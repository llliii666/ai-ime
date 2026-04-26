from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
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
        icon.title = f"AI IME - {'listening' if logger.running else 'paused'}"
        icon.menu = pystray.Menu(
            pystray.MenuItem("Settings", show_settings, default=True),
            pystray.MenuItem("Pause listener" if logger.running else "Start listener", toggle_listener),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
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
                _show_error(f"Keyboard listener failed: {exc}")
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
    root.title("AI IME Settings")
    root.geometry("620x430")
    root.resizable(True, True)

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

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=12)

    general = ttk.Frame(notebook, padding=12)
    model = ttk.Frame(notebook, padding=12)
    rime = ttk.Frame(notebook, padding=12)
    notebook.add(general, text="General")
    notebook.add(model, text="Model")
    notebook.add(rime, text="Rime")

    _check(general, "Enable listener", listener_enabled, 0)
    _check(general, "Record full local keylog", record_full_keylog, 1)
    _check(general, "Allow sending full keylog", send_full_keylog, 2)
    _check(general, "Start on Windows login", start_on_login, 3)
    _entry(general, "Keylog file", keylog_file, 4)

    _combo(model, "Provider", provider, ["openai-compatible", "ollama", "mock"], 0)
    _entry(model, "OpenAI-compatible base URL", openai_base_url, 1)
    _entry(model, "OpenAI-compatible model", openai_model, 2)
    _entry(model, "OpenAI-compatible API key", openai_api_key, 3, show="*")
    _entry(model, "Ollama base URL", ollama_base_url, 4)
    _entry(model, "Ollama model", ollama_model, 5)

    _entry(rime, "Rime user directory", rime_dir, 0)
    _entry(rime, "Schema", rime_schema, 1)
    _entry(rime, "Generated dictionary", rime_dictionary, 2)
    _entry(rime, "Base dictionary", rime_base_dictionary, 3)

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

    buttons = ttk.Frame(root, padding=(12, 0, 12, 12))
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Save", command=save).pack(side="right")
    ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right", padx=(0, 8))
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


def _entry(parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, show: str | None = None) -> None:
    parent.columnconfigure(1, weight=1)
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
    ttk.Entry(parent, textvariable=variable, show=show or "").grid(row=row, column=1, sticky="ew", pady=6)


def _combo(parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str], row: int) -> None:
    parent.columnconfigure(1, weight=1)
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
    ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").grid(row=row, column=1, sticky="ew", pady=6)


def _check(parent: ttk.Frame, label: str, variable: tk.BooleanVar, row: int) -> None:
    ttk.Checkbutton(parent, text=label, variable=variable).grid(row=row, column=0, columnspan=2, sticky="w", pady=6)


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
