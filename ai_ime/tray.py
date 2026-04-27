from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pystray
from PIL import Image, ImageDraw, ImageFont

from ai_ime.analysis_scheduler import AdaptiveAnalysisScheduler
from ai_ime.config import default_data_dir, load_env_file
from ai_ime.icons import app_icon_path
from ai_ime.learning import AutoLearningEngine
from ai_ime.listener import KeyLogEntry, KeyLogWriter
from ai_ime.rime.paths import detect_preferred_schema, find_existing_user_dir
from ai_ime.runtime import acquire_single_instance, clear_pid_file, write_pid_file
from ai_ime.settings import AppSettings, load_app_settings, resolved_keylog_path, save_app_settings
from ai_ime.signals import default_settings_show_signal_path, default_settings_updated_signal_path, touch_signal
from ai_ime.startup import default_project_root, default_pythonw_executable, sync_start_on_login


class KeyboardLogger:
    def __init__(self) -> None:
        self._hook: Any = None
        self._keyboard: Any = None
        self._learning: AutoLearningEngine | None = None
        self._analysis_scheduler: AdaptiveAnalysisScheduler | None = None

    @property
    def running(self) -> bool:
        return self._hook is not None

    def start(self, settings: AppSettings) -> None:
        if self.running:
            return
        import keyboard  # type: ignore[import-not-found]

        self._keyboard = keyboard
        self._learning = AutoLearningEngine(settings)
        if settings.auto_analyze_with_ai:
            self._analysis_scheduler = AdaptiveAnalysisScheduler(settings)
            self._analysis_scheduler.start()
        writer = KeyLogWriter(resolved_keylog_path(settings))

        def on_event(event: Any) -> None:
            event_type = str(getattr(event, "event_type", ""))
            name = str(getattr(event, "name", ""))
            if not settings.record_full_keylog:
                if self._learning is not None:
                    self._learning.handle_key_event(event_type, name)
                return
            if settings.record_full_keylog:
                writer.write(
                    KeyLogEntry(
                        timestamp=time.time(),
                        event_type=event_type,
                        name=name,
                        scan_code=getattr(event, "scan_code", None),
                    )
                )
            if self._learning is not None:
                self._learning.handle_key_event(event_type, name)

        self._hook = keyboard.hook(on_event)

    def stop(self) -> None:
        if self._hook is not None and self._keyboard is not None:
            self._keyboard.unhook(self._hook)
        self._hook = None
        self._learning = None
        if self._analysis_scheduler is not None:
            self._analysis_scheduler.stop()
        self._analysis_scheduler = None


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path(".env"))
    if not acquire_single_instance():
        return 0
    write_pid_file()

    settings = prepare_settings(load_app_settings())
    sync_start_on_login(settings.start_on_login)
    logger = KeyboardLogger()
    _apply_listener_settings(logger, settings)
    settings_window = SettingsWindowController()

    icon = pystray.Icon("ai-ime", _build_icon(), "AI IME")

    def refresh_menu() -> None:
        state = "监听中" if logger.running else "已暂停"
        icon.title = f"AI IME - {state}"
        icon.menu = pystray.Menu(
            pystray.MenuItem("打开设置", show_settings, default=True),
            pystray.MenuItem("暂停监听" if logger.running else "开始监听", toggle_listener),
            pystray.MenuItem("重新加载配置", reload_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", quit_app),
        )
        icon.update_menu()

    def reload_settings(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        nonlocal settings
        load_env_file(Path(".env"), override=True)
        settings = prepare_settings(load_app_settings())
        _apply_listener_settings(logger, settings)
        refresh_menu()

    settings_watcher = SettingsReloadWatcher(default_settings_updated_signal_path(), reload_settings)
    settings_watcher.start()

    def show_settings(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        try:
            settings_window.open()
        except Exception as exc:
            _show_error(f"设置窗口启动失败：{exc}")

    def toggle_listener(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        settings.listener_enabled = not logger.running
        _apply_listener_settings(logger, settings)
        save_app_settings(settings)
        refresh_menu()

    def quit_app(_icon: pystray.Icon | None = None, _item: pystray.MenuItem | None = None) -> None:
        settings_watcher.stop()
        settings_window.stop()
        logger.stop()
        clear_pid_file()
        icon.stop()

    try:
        refresh_menu()
        icon.run()
        return 0
    finally:
        settings_watcher.stop()
        settings_window.stop()
        logger.stop()
        clear_pid_file()


def prepare_settings(settings: AppSettings) -> AppSettings:
    if not settings.rime_dir:
        detected = find_existing_user_dir()
        if detected is not None:
            settings.rime_dir = str(detected)
    if settings.rime_dir:
        detected_schema = detect_preferred_schema(Path(settings.rime_dir))
        if detected_schema and settings.rime_schema in {"", "luna_pinyin", "rime_ice"}:
            settings.rime_schema = detected_schema
    return settings


class SettingsWindowController:
    def __init__(
        self,
        signal_path: Path | None = None,
        command: list[str] | None = None,
    ) -> None:
        self.signal_path = signal_path or default_settings_show_signal_path()
        self.command = command
        self.process: subprocess.Popen[object] | None = None

    def open(self) -> None:
        if self.process is not None and self.process.poll() is None:
            touch_signal(self.signal_path)
            return
        self.process = open_settings_window_process(command=self.command, signal_path=self.signal_path)

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()


class SettingsReloadWatcher:
    def __init__(self, signal_path: Path, callback: Any, poll_interval: float = 0.5) -> None:
        self.signal_path = signal_path
        self.callback = callback
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_seen = _signal_mtime(signal_path)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AIIMESettingsReloadWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            current = _signal_mtime(self.signal_path)
            if current <= self._last_seen:
                continue
            self._last_seen = current
            self.callback()


def open_settings_window_process(command: list[str] | None = None, signal_path: Path | None = None) -> subprocess.Popen[object]:
    log_file = default_data_dir() / "settings-window.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log = log_file.open("a", encoding="utf-8", newline="\n")
    try:
        process = subprocess.Popen(
            command or build_settings_window_command(signal_path=signal_path, persistent=True),
            cwd=runtime_working_directory(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=_detached_creationflags(),
            close_fds=True,
        )
    except Exception:
        log.close()
        raise
    log.close()
    return process


def build_settings_window_command(signal_path: Path | None = None, persistent: bool = False) -> list[str]:
    if getattr(sys, "frozen", False):
        command = [str(Path(sys.executable)), "--settings-window"]
    else:
        command = [_pythonw_executable(), "-m", "ai_ime.settings_window"]
    if persistent:
        if getattr(sys, "frozen", False):
            command.append("--settings-persistent")
            command.extend(["--settings-show-signal", str(signal_path or default_settings_show_signal_path())])
        else:
            command.append("--persistent")
            command.extend(["--show-signal", str(signal_path or default_settings_show_signal_path())])
    return command


def _apply_listener_settings(logger: KeyboardLogger, settings: AppSettings) -> None:
    logger.stop()
    if not settings.listener_enabled:
        return
    try:
        logger.start(settings)
    except Exception as exc:
        _show_error(f"键盘监听启动失败：{exc}")


def _pythonw_executable() -> str:
    return str(default_pythonw_executable(runtime_working_directory()))


def runtime_working_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return default_project_root().resolve()


def _detached_creationflags() -> int:
    if not sys.platform.startswith("win"):
        return 0
    return subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def _signal_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _build_icon() -> Image.Image:
    try:
        return Image.open(app_icon_path()).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    except Exception:
        pass
    image = Image.new("RGB", (64, 64), "#101828")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill="#ffffff")
    draw.text((18, 20), "AI", fill="#101828", font=font)
    return image


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("AI IME", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
