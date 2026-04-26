from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageDraw, ImageFont
import pystray

from ai_ime.config import load_env_file
from ai_ime.listener import KeyLogEntry, KeyLogWriter
from ai_ime.rime.paths import detect_active_schema, find_existing_user_dir
from ai_ime.runtime import clear_pid_file, write_pid_file
from ai_ime.settings import AppSettings, env_api_key, load_app_settings, save_app_settings, write_provider_env
from ai_ime.startup import set_start_on_login


class KeyboardLogger:
    def __init__(self) -> None:
        self._hook: Any = None
        self._keyboard: Any = None

    @property
    def running(self) -> bool:
        return self._hook is not None

    def start(self, settings: AppSettings) -> None:
        if self.running:
            return
        import keyboard  # type: ignore[import-not-found]

        self._keyboard = keyboard
        writer = KeyLogWriter(Path(settings.keylog_file))

        def on_event(event: Any) -> None:
            if not settings.record_full_keylog:
                return
            writer.write(
                KeyLogEntry(
                    timestamp=time.time(),
                    event_type=str(getattr(event, "event_type", "")),
                    name=str(getattr(event, "name", "")),
                    scan_code=getattr(event, "scan_code", None),
                )
            )

        self._hook = keyboard.hook(on_event)

    def stop(self) -> None:
        if self._hook is not None and self._keyboard is not None:
            self._keyboard.unhook(self._hook)
        self._hook = None


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path(".env"))
    write_pid_file()

    settings = load_app_settings()
    if not settings.rime_dir:
        detected = find_existing_user_dir()
        if detected is not None:
            settings.rime_dir = str(detected)
    if settings.rime_dir:
        detected_schema = detect_active_schema(Path(settings.rime_dir))
        if detected_schema and settings.rime_schema in {"", "luna_pinyin"}:
            settings.rime_schema = detected_schema

    logger = KeyboardLogger()
    if settings.listener_enabled:
        try:
            logger.start(settings)
        except Exception as exc:
            _show_error(f"Keyboard listener failed: {exc}")

    icon = pystray.Icon("ai-ime", _build_icon(), "AI IME")

    def refresh_menu() -> None:
        icon.title = f"AI IME - {'监听中' if logger.running else '已暂停'}"
        icon.menu = pystray.Menu(
            pystray.MenuItem("打开设置", show_settings, default=True),
            pystray.MenuItem("暂停监听" if logger.running else "开始监听", toggle_listener),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", quit_app),
        )
        icon.update_menu()

    def show_settings(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        nonlocal settings
        result = open_settings_window(settings)
        if result is None:
            return
        settings, api_key = result
        save_app_settings(settings)
        write_provider_env(settings, api_key=api_key)
        set_start_on_login(settings.start_on_login)
        logger.stop()
        if settings.listener_enabled:
            try:
                logger.start(settings)
            except Exception as exc:
                _show_error(f"键盘监听启动失败：{exc}")
        refresh_menu()

    def toggle_listener(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        settings.listener_enabled = not logger.running
        logger.stop()
        if settings.listener_enabled:
            try:
                logger.start(settings)
            except Exception as exc:
                _show_error(f"Keyboard listener failed: {exc}")
        save_app_settings(settings)
        refresh_menu()

    def quit_app(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        logger.stop()
        clear_pid_file()
        icon.stop()

    try:
        refresh_menu()
        icon.run()
        return 0
    finally:
        logger.stop()
        clear_pid_file()


def open_settings_window(initial: AppSettings) -> tuple[AppSettings, str] | None:
    root = tk.Tk()
    root.title("AI IME 设置")
    root.geometry("980x680")
    root.minsize(880, 620)
    root.resizable(True, True)
    root.configure(bg="#edf1f7")
    root.option_add("*Font", "{Microsoft YaHei UI} 10")
    _apply_settings_style(root)

    listener_enabled = tk.BooleanVar(value=initial.listener_enabled)
    record_full_keylog = tk.BooleanVar(value=initial.record_full_keylog)
    send_full_keylog = tk.BooleanVar(value=initial.send_full_keylog)
    start_on_login = tk.BooleanVar(value=initial.start_on_login)
    provider = tk.StringVar(value=initial.provider)
    openai_base_url = tk.StringVar(value=initial.openai_base_url)
    openai_model = tk.StringVar(value=initial.openai_model)
    openai_api_key = tk.StringVar(value=env_api_key(initial))
    ollama_base_url = tk.StringVar(value=initial.ollama_base_url)
    ollama_model = tk.StringVar(value=initial.ollama_model)
    rime_dir = tk.StringVar(value=initial.rime_dir)
    rime_schema = tk.StringVar(value=initial.rime_schema)
    rime_dictionary = tk.StringVar(value=initial.rime_dictionary)
    rime_base_dictionary = tk.StringVar(value=initial.rime_base_dictionary)
    keylog_file = tk.StringVar(value=initial.keylog_file)

    shell = ttk.Frame(root, style="Shell.TFrame", padding=18)
    shell.pack(fill="both", expand=True)
    shell.columnconfigure(1, weight=1)
    shell.rowconfigure(1, weight=1)

    header = ttk.Frame(shell, style="Shell.TFrame")
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
    header.columnconfigure(1, weight=1)
    tk.Label(
        header,
        text="AI",
        bg="#111827",
        fg="#ffffff",
        width=4,
        height=2,
        font=("Microsoft YaHei UI", 14, "bold"),
    ).grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 14))
    ttk.Label(header, text="AI IME 设置", style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="sw")
    ttk.Label(header, text="输入习惯学习、模型供应商与 Rime 接入", style="HeaderSubtle.TLabel").grid(
        row=1, column=1, sticky="nw", pady=(2, 0)
    )
    _status_pill(header, "监听", "开启" if initial.listener_enabled else "暂停").grid(
        row=0, column=2, rowspan=2, padx=(10, 0)
    )
    _status_pill(header, "方案", initial.rime_schema or "未设置").grid(row=0, column=3, rowspan=2, padx=(10, 0))

    sidebar = tk.Frame(shell, bg="#111827", width=210, highlightthickness=0)
    sidebar.grid(row=1, column=0, sticky="ns", padx=(0, 16))
    sidebar.grid_propagate(False)

    content = ttk.Frame(shell, style="Shell.TFrame")
    content.grid(row=1, column=1, sticky="nsew")
    content.columnconfigure(0, weight=1)
    content.rowconfigure(0, weight=1)

    pages: dict[str, ttk.Frame] = {}
    nav_buttons: dict[str, tk.Button] = {}

    general_page = _page(content)
    pages["常规"] = general_page
    _page_title(general_page, "常规", "后台运行与启动行为", 0)
    overview = ttk.Frame(general_page, style="Shell.TFrame")
    overview.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    overview.columnconfigure((0, 1, 2), weight=1, uniform="overview")
    _overview_item(overview, "监听状态", "开启" if initial.listener_enabled else "暂停", 0)
    _overview_item(overview, "模型通道", _provider_label(initial.provider), 1)
    _overview_item(overview, "输入方案", initial.rime_schema or "未设置", 2)
    runtime_section = _section(general_page, "后台运行", 3)
    _check(runtime_section, "启用键盘监听", listener_enabled, 0)
    _check(runtime_section, "开机自动启动", start_on_login, 1)
    _path_field(runtime_section, "键盘日志文件", keylog_file, 2, mode="file")

    privacy_page = _page(content)
    pages["隐私"] = privacy_page
    _page_title(privacy_page, "隐私", "本地记录与模型上传边界", 0)
    privacy_section = _section(privacy_page, "键入数据", 2)
    _check(privacy_section, "记录完整本地键盘日志", record_full_keylog, 0)
    _check(privacy_section, "允许向模型发送完整键入记录", send_full_keylog, 1)
    notice = ttk.Frame(privacy_page, style="Notice.TFrame", padding=(16, 14))
    notice.grid(row=3, column=0, sticky="ew", pady=(12, 0))
    notice.columnconfigure(0, weight=1)
    ttk.Label(notice, text="本地模型可使用完整日志；云端或中转模型是否发送完整日志由这里控制。", style="Notice.TLabel").grid(
        row=0, column=0, sticky="w"
    )

    model_page = _page(content)
    pages["模型"] = model_page
    _page_title(model_page, "模型", "供应商、模型名与调用地址", 0)
    provider_section = _section(model_page, "供应商", 2)
    _combo(provider_section, "当前通道", provider, ["openai-compatible", "ollama", "mock"], 0)
    openai_section = _section(model_page, "OpenAI 兼容接口", 3)
    _entry(openai_section, "Base URL", openai_base_url, 0)
    _entry(openai_section, "模型", openai_model, 1)
    _entry(openai_section, "API Key", openai_api_key, 2, show="*")
    ollama_section = _section(model_page, "Ollama 本地模型", 4)
    _entry(ollama_section, "Base URL", ollama_base_url, 0)
    _entry(ollama_section, "模型", ollama_model, 1)

    rime_page = _page(content)
    pages["输入法"] = rime_page
    _page_title(rime_page, "输入法", "小狼毫 Rime 接入配置", 0)
    rime_section = _section(rime_page, "Rime 用户目录", 2)
    _path_field(rime_section, "目录", rime_dir, 0, mode="directory")
    _entry(rime_section, "方案 ID", rime_schema, 1)
    _entry(rime_section, "纠错词典", rime_dictionary, 2)
    _entry(rime_section, "可选导入词典", rime_base_dictionary, 3)
    ttk.Button(rime_section, text="自动检测 Rime", style="Secondary.TButton", command=lambda: _detect_rime(rime_dir, rime_schema)).grid(
        row=4, column=1, sticky="w", pady=(10, 0)
    )

    result: dict[str, tuple[AppSettings, str] | None] = {"value": None}

    def save() -> None:
        result["value"] = (
            AppSettings(
                listener_enabled=listener_enabled.get(),
                record_full_keylog=record_full_keylog.get(),
                send_full_keylog=send_full_keylog.get(),
                start_on_login=start_on_login.get(),
                provider=provider.get(),
                openai_base_url=openai_base_url.get().strip(),
                openai_model=openai_model.get().strip() or "gpt-5.4-mini",
                openai_api_key_env="AI_IME_OPENAI_API_KEY",
                ollama_base_url=ollama_base_url.get().strip() or "http://localhost:11434",
                ollama_model=ollama_model.get().strip(),
                rime_dir=rime_dir.get().strip(),
                rime_schema=rime_schema.get().strip() or "luna_pinyin",
                rime_dictionary=rime_dictionary.get().strip() or "ai_typo",
                rime_base_dictionary=rime_base_dictionary.get().strip(),
                keylog_file=keylog_file.get().strip(),
            ),
            openai_api_key.get(),
        )
        root.destroy()

    def cancel() -> None:
        root.destroy()

    def show_page(name: str) -> None:
        for page in pages.values():
            page.grid_remove()
        pages[name].grid(row=0, column=0, sticky="nsew")
        for label, button in nav_buttons.items():
            selected = label == name
            button.configure(
                bg="#2563eb" if selected else "#111827",
                fg="#ffffff" if selected else "#cbd5e1",
                activebackground="#2563eb" if selected else "#1f2937",
            )

    for index, label in enumerate(["常规", "隐私", "模型", "输入法"]):
        nav_buttons[label] = _nav_button(sidebar, label, lambda value=label: show_page(value), index)
    show_page("常规")

    buttons = ttk.Frame(shell, style="Shell.TFrame")
    buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    buttons.columnconfigure(0, weight=1)
    ttk.Button(buttons, text="保存设置", style="Primary.TButton", command=save).grid(row=0, column=2, sticky="e")
    ttk.Button(buttons, text="取消", style="Secondary.TButton", command=cancel).grid(row=0, column=1, sticky="e", padx=(0, 10))
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()
    return result["value"]


def _build_icon() -> Image.Image:
    image = Image.new("RGB", (64, 64), "#1f2937")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    draw.text((15, 18), "AI", fill="#f9fafb", font=font)
    return image


def _apply_settings_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Shell.TFrame", background="#edf1f7")
    style.configure("Card.TFrame", background="#ffffff", relief="flat")
    style.configure("Notice.TFrame", background="#e8f1ff", relief="flat")
    style.configure("HeaderTitle.TLabel", background="#edf1f7", foreground="#0f172a", font=("Microsoft YaHei UI", 20, "bold"))
    style.configure("HeaderSubtle.TLabel", background="#edf1f7", foreground="#64748b", font=("Microsoft YaHei UI", 10))
    style.configure("PageTitle.TLabel", background="#edf1f7", foreground="#0f172a", font=("Microsoft YaHei UI", 18, "bold"))
    style.configure("PageSubtle.TLabel", background="#edf1f7", foreground="#64748b")
    style.configure("SectionTitle.TLabel", background="#ffffff", foreground="#111827", font=("Microsoft YaHei UI", 12, "bold"))
    style.configure("Field.TLabel", background="#ffffff", foreground="#475569")
    style.configure("Notice.TLabel", background="#e8f1ff", foreground="#1e3a8a")
    style.configure("Value.TLabel", background="#ffffff", foreground="#0f172a", font=("Microsoft YaHei UI", 13, "bold"))
    style.configure("TCheckbutton", background="#ffffff", foreground="#0f172a", padding=(0, 5))
    style.map("TCheckbutton", background=[("active", "#ffffff")])
    style.configure("TEntry", padding=(10, 7), fieldbackground="#f8fafc")
    style.configure("TCombobox", padding=(8, 6), fieldbackground="#f8fafc")
    style.configure("Primary.TButton", padding=(18, 9), background="#2563eb", foreground="#ffffff", font=("Microsoft YaHei UI", 10, "bold"))
    style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")], foreground=[("active", "#ffffff")])
    style.configure("Secondary.TButton", padding=(14, 8), background="#ffffff", foreground="#334155")
    style.map("Secondary.TButton", background=[("active", "#e2e8f0"), ("pressed", "#cbd5e1")])


def _page(parent: ttk.Frame) -> ttk.Frame:
    frame = ttk.Frame(parent, style="Shell.TFrame")
    frame.columnconfigure(0, weight=1)
    return frame


def _page_title(parent: ttk.Frame, title: str, subtitle: str, row: int) -> None:
    ttk.Label(parent, text=title, style="PageTitle.TLabel").grid(row=row, column=0, sticky="w")
    ttk.Label(parent, text=subtitle, style="PageSubtle.TLabel").grid(row=row + 1, column=0, sticky="w", pady=(2, 14))


def _section(parent: ttk.Frame, title: str, row: int) -> ttk.Frame:
    outer = ttk.Frame(parent, style="Card.TFrame", padding=(18, 16))
    outer.grid(row=row, column=0, sticky="ew", pady=(0, 12))
    outer.columnconfigure(1, weight=1)
    ttk.Label(outer, text=title, style="SectionTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
    body = ttk.Frame(outer, style="Card.TFrame")
    body.grid(row=1, column=0, columnspan=3, sticky="ew")
    body.columnconfigure(1, weight=1)
    return body


def _overview_item(parent: ttk.Frame, label: str, value: str, column: int) -> None:
    card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 14))
    card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
    ttk.Label(card, text=label, style="Field.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(card, text=value, style="Value.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))


def _status_pill(parent: ttk.Frame, label: str, value: str) -> tk.Label:
    return tk.Label(
        parent,
        text=f"{label}  {value}",
        bg="#dbeafe",
        fg="#1e40af",
        padx=14,
        pady=7,
        font=("Microsoft YaHei UI", 9, "bold"),
    )


def _nav_button(parent: tk.Frame, text: str, command: Any, row: int) -> tk.Button:
    button = tk.Button(
        parent,
        text=text,
        command=command,
        anchor="w",
        bd=0,
        padx=22,
        pady=13,
        bg="#111827",
        fg="#cbd5e1",
        activebackground="#1f2937",
        activeforeground="#ffffff",
        font=("Microsoft YaHei UI", 11, "bold"),
        cursor="hand2",
    )
    button.grid(row=row, column=0, sticky="ew", pady=(10 if row == 0 else 0, 0))
    parent.columnconfigure(0, weight=1)
    return button


def _entry(parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, show: str | None = None) -> None:
    parent.columnconfigure(1, weight=1)
    ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7, padx=(0, 16))
    ttk.Entry(parent, textvariable=variable, show=show or "").grid(row=row, column=1, sticky="ew", pady=7)


def _combo(parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str], row: int) -> None:
    parent.columnconfigure(1, weight=1)
    ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7, padx=(0, 16))
    ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").grid(row=row, column=1, sticky="ew", pady=7)


def _check(parent: ttk.Frame, label: str, variable: tk.BooleanVar, row: int) -> None:
    ttk.Checkbutton(parent, text=label, variable=variable).grid(row=row, column=0, columnspan=2, sticky="w", pady=5)


def _path_field(parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, mode: str) -> None:
    parent.columnconfigure(1, weight=1)
    ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=7, padx=(0, 16))
    ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=7)
    ttk.Button(
        parent,
        text="浏览",
        style="Secondary.TButton",
        command=lambda: _browse_path(variable, mode=mode),
    ).grid(row=row, column=2, sticky="e", padx=(10, 0), pady=7)


def _browse_path(variable: tk.StringVar, mode: str) -> None:
    current = variable.get().strip()
    if mode == "directory":
        selected = filedialog.askdirectory(initialdir=current or str(Path.home()))
    else:
        selected = filedialog.asksaveasfilename(initialfile=Path(current).name if current else "keylog.jsonl")
    if selected:
        variable.set(selected)


def _detect_rime(rime_dir: tk.StringVar, rime_schema: tk.StringVar) -> None:
    detected = find_existing_user_dir()
    if detected is None:
        _show_error("没有检测到 Rime 用户目录。")
        return
    rime_dir.set(str(detected))
    detected_schema = detect_active_schema(detected)
    if detected_schema:
        rime_schema.set(detected_schema)


def _provider_label(value: str) -> str:
    labels = {
        "openai-compatible": "OpenAI 兼容",
        "ollama": "Ollama",
        "mock": "本地模拟",
    }
    return labels.get(value, value or "未设置")


def _show_error(message: str) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("AI IME", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
