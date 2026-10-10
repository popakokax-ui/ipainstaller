import threading
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import core


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("IPA Installer")
        self.geometry("560x560")
        self.devices: list[core.Device] = []

        self.ipa = tk.StringVar()
        self.p12 = tk.StringVar()
        self.pw = tk.StringVar()
        self.prof = tk.StringVar()
        self.do_sign = tk.BooleanVar(value=False)

        pad = {"padx": 10, "pady": 4}
        f = ttk.Frame(self)
        f.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(f, text="1. iPhone (подключи по USB и разблокируй)").pack(anchor="w", **pad)
        row = ttk.Frame(f)
        row.pack(fill="x", **pad)
        self.combo = ttk.Combobox(row, state="readonly")
        self.combo.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Обновить", command=self.refresh).pack(side="left", padx=(6, 0))

        ttk.Label(f, text="2. Файл IPA").pack(anchor="w", **pad)
        self._picker(f, self.ipa, [("IPA", "*.ipa")])

        ttk.Checkbutton(f, text="3. Подписать перед установкой (свой сертификат)",
                        variable=self.do_sign, command=self._toggle).pack(anchor="w", **pad)
        self.sign_box = ttk.Frame(f)
        self.sign_box.pack(fill="x")
        ttk.Label(self.sign_box, text="Сертификат .p12").pack(anchor="w", padx=10)
        self._picker(self.sign_box, self.p12, [("P12", "*.p12")])
        ttk.Label(self.sign_box, text="Пароль от .p12").pack(anchor="w", padx=10)
        ttk.Entry(self.sign_box, textvariable=self.pw, show="*").pack(fill="x", padx=10, pady=2)
        ttk.Label(self.sign_box, text="Профиль .mobileprovision").pack(anchor="w", padx=10)
        self._picker(self.sign_box, self.prof, [("Profile", "*.mobileprovision")])
        self._toggle()

        self.btn = ttk.Button(f, text="Установить", command=self.install)
        self.btn.pack(fill="x", padx=10, pady=10)
        self.bar = ttk.Progressbar(f, maximum=100)
        self.bar.pack(fill="x", padx=10)
        self.log = tk.Text(f, height=8, state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=8)

        self.after(200, self.refresh)

    def _picker(self, parent, var, types) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=10, pady=2)
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Выбрать…", command=lambda: var.set(
            filedialog.askopenfilename(filetypes=types) or var.get())).pack(side="left", padx=(6, 0))

    def _toggle(self) -> None:
        state = "normal" if self.do_sign.get() else "disabled"
        for w in self.sign_box.winfo_children():
            self._set_state(w, state)

    def _set_state(self, w, state) -> None:
        try:
            w.configure(state=state)
        except tk.TclError:
            pass
        for c in w.winfo_children():
            self._set_state(c, state)

    def say(self, text: str) -> None:
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(0, _do)

    def run_bg(self, fn) -> None:
        self.btn.configure(state="disabled")

        def worker():
            try:
                fn()
            except Exception as e:
                self.say(f"Ошибка: {e}")
                self.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
            finally:
                self.after(0, lambda: self.btn.configure(state="normal"))
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self) -> None:
        def job():
            self.devices = core.list_devices()
            names = [str(d) for d in self.devices]
            self.after(0, lambda: (self.combo.configure(values=names),
                                   self.combo.current(0) if names else self.combo.set("")))
            self.say(f"Найдено устройств: {len(names)}")
        self.run_bg(job)

    def install(self) -> None:
        idx = self.combo.current()
        if idx < 0 or idx >= len(self.devices):
            messagebox.showwarning("iPhone", "Сначала подключи iPhone и нажми «Обновить».")
            return
        device, ipa = self.devices[idx], self.ipa.get()

        def job():
            core.check_ipa(ipa)
            target = ipa
            if self.do_sign.get():
                if not (self.p12.get() and self.prof.get()):
                    raise ValueError("Укажи .p12 и .mobileprovision")
                target = str(Path(tempfile.mkdtemp()) / "signed.ipa")
                self.say("Подписываю IPA…")
                core.sign_ipa(ipa, self.p12.get(), self.pw.get(), self.prof.get(), target)
            self.say(f"Устанавливаю на {device.name}…")
            core.install_ipa(device.udid, target,
                             lambda p: self.after(0, lambda: self.bar.configure(value=p)))
            self.say("Готово: приложение установлено.")
        self.run_bg(job)


if __name__ == "__main__":
    App().mainloop()
