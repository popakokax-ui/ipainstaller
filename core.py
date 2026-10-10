"""Ядро: поиск iPhone по USB, подпись IPA (через zsign) и установка."""
import asyncio
import inspect
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Device:
    udid: str
    name: str
    ios: str

    def __str__(self) -> str:
        return f"{self.name} (iOS {self.ios})"


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def find_zsign() -> Optional[str]:
    for name in ("zsign.exe", "zsign"):
        p = _app_dir() / name
        if p.exists():
            return str(p)
    return shutil.which("zsign")


async def _close(obj) -> None:
    r = obj.close()
    if inspect.isawaitable(r):
        await r


async def _list_devices() -> list[Device]:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.usbmux import list_devices

    result: list[Device] = []
    for d in await list_devices():
        ld = await create_using_usbmux(serial=d.serial)
        try:
            info = ld.short_info
            result.append(Device(d.serial, info.get("DeviceName", "iPhone"),
                                 info.get("ProductVersion", "?")))
        finally:
            await _close(ld)
    return result


def list_devices() -> list[Device]:
    from pymobiledevice3.exceptions import MuxException

    try:
        return asyncio.run(_list_devices())
    except (ConnectionError, OSError, MuxException) as e:
        raise RuntimeError(
            "Не удалось связаться со службой USB для iPhone. "
            "На Windows установи iTunes или приложение Apple Devices и подключи телефон."
        ) from e


def check_ipa(path: str) -> None:
    p = Path(path)
    if p.suffix.lower() != ".ipa" or not p.is_file():
        raise ValueError("Выбери файл с расширением .ipa")
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
    except zipfile.BadZipFile as e:
        raise ValueError("Файл повреждён: это не IPA (zip-архив)") from e
    if not any(n.startswith("Payload/") and ".app/" in n for n in names):
        raise ValueError("В архиве нет Payload/*.app: это не приложение для iOS")


def sign_ipa(ipa: str, p12: str, password: str, profile: str, out: str) -> None:
    z = find_zsign()
    if not z:
        raise RuntimeError("zsign не найден. Положи zsign.exe рядом с программой (см. README).")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    r = subprocess.run([z, "-k", p12, "-p", password, "-m", profile, "-o", out, ipa],
                       capture_output=True, text=True, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError("Подпись не удалась:\n" + (r.stdout + r.stderr).strip())


async def _install(udid: str, ipa: str, progress: Callable[[int], None]) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    ld = await create_using_usbmux(serial=udid)
    try:
        svc = InstallationProxyService(ld)
        await svc.install_from_local(ipa, handler=lambda pct, *a: progress(int(pct)))
    finally:
        await _close(ld)


def install_ipa(udid: str, ipa: str, progress: Callable[[int], None]) -> None:
    try:
        asyncio.run(_install(udid, ipa, progress))
    except Exception as e:  # понятное сообщение для типичных причин
        text = str(e)
        hint = ""
        if "MismatchedApplicationIdentifierEntitlement" in text or "signature" in text.lower():
            hint = "\nВероятно, IPA не подписан или подпись не подходит этому iPhone."
        raise RuntimeError(f"Установка не удалась: {text}{hint}") from e
