from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from ai_ime.config import load_env_file
from ai_ime.listener import KeyLogEntry, KeyLogWriter
from ai_ime.rime.paths import find_existing_user_dir
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
    from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

    app = QApplication(argv or sys.argv)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "AI IME", "System tray is not available.")
        return 1
    app.setQuitOnLastWindowClosed(False)

    settings = load_app_settings()
    if not settings.rime_dir:
        detected = find_existing_user_dir()
        if detected is not None:
            settings.rime_dir = str(detected)

    logger = KeyboardLogger()
    if settings.listener_enabled:
        try:
            logger.start(settings)
        except Exception as exc:  # UI boundary: show the error instead of crashing.
            QMessageBox.warning(None, "AI IME", f"Keyboard listener failed: {exc}")

    icon = _build_icon(QPixmap, QPainter, QColor, QFont, QIcon)
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("AI IME")
    menu = QMenu()

    settings_action = QAction("Settings")
    toggle_action = QAction("Pause listener" if logger.running else "Start listener")
    quit_action = QAction("Quit")
    menu.addAction(settings_action)
    menu.addAction(toggle_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    def update_toggle_text() -> None:
        toggle_action.setText("Pause listener" if logger.running else "Start listener")
        tray.setToolTip(f"AI IME - {'listening' if logger.running else 'paused'}")

    def show_settings() -> None:
        nonlocal settings
        dialog = SettingsDialog(settings)
        if dialog.exec():
            settings = dialog.to_settings()
            save_app_settings(settings)
            write_provider_env(settings, api_key=dialog.api_key())
            set_start_on_login(settings.start_on_login)
            if settings.listener_enabled:
                logger.stop()
                logger.start(settings)
            else:
                logger.stop()
            update_toggle_text()

    def toggle_listener() -> None:
        settings.listener_enabled = not logger.running
        if settings.listener_enabled:
            logger.start(settings)
        else:
            logger.stop()
        save_app_settings(settings)
        update_toggle_text()

    def quit_app() -> None:
        logger.stop()
        app.quit()

    settings_action.triggered.connect(show_settings)
    toggle_action.triggered.connect(toggle_listener)
    quit_action.triggered.connect(quit_app)
    tray.activated.connect(lambda reason: show_settings() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    update_toggle_text()
    tray.show()
    return app.exec()


def _build_icon(QPixmap: Any, QPainter: Any, QColor: Any, QFont: Any, QIcon: Any) -> Any:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#1f2937"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#f9fafb"))
    font = QFont("Segoe UI", 20)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x84, "AI")
    painter.end()
    return QIcon(pixmap)


class SettingsDialog:  # Wrapper replaced at runtime to avoid importing PySide6 during tests.
    def __new__(cls, settings: AppSettings) -> Any:
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLineEdit,
            QPushButton,
            QTabWidget,
            QVBoxLayout,
            QWidget,
        )

        class _Dialog(QDialog):
            def __init__(self, initial: AppSettings) -> None:
                super().__init__()
                self.setWindowTitle("AI IME Settings")
                self.resize(560, 420)

                self.listener_enabled = QCheckBox()
                self.listener_enabled.setChecked(initial.listener_enabled)
                self.record_full_keylog = QCheckBox()
                self.record_full_keylog.setChecked(initial.record_full_keylog)
                self.send_full_keylog = QCheckBox()
                self.send_full_keylog.setChecked(initial.send_full_keylog)
                self.start_on_login = QCheckBox()
                self.start_on_login.setChecked(initial.start_on_login)

                self.provider = QComboBox()
                self.provider.addItems(["openai-compatible", "ollama", "mock"])
                self.provider.setCurrentText(initial.provider)
                self.openai_base_url = QLineEdit(initial.openai_base_url)
                self.openai_model = QLineEdit(initial.openai_model)
                self.openai_api_key = QLineEdit(env_api_key(initial))
                self.openai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
                self.ollama_base_url = QLineEdit(initial.ollama_base_url)
                self.ollama_model = QLineEdit(initial.ollama_model)

                self.rime_dir = QLineEdit(initial.rime_dir)
                self.rime_schema = QLineEdit(initial.rime_schema)
                self.rime_dictionary = QLineEdit(initial.rime_dictionary)
                self.rime_base_dictionary = QLineEdit(initial.rime_base_dictionary)
                self.keylog_file = QLineEdit(initial.keylog_file)

                tabs = QTabWidget()
                tabs.addTab(_form_tab(QFormLayout, QWidget, [
                    ("Enable listener", self.listener_enabled),
                    ("Record full local keylog", self.record_full_keylog),
                    ("Allow sending full keylog", self.send_full_keylog),
                    ("Start on Windows login", self.start_on_login),
                    ("Keylog file", self.keylog_file),
                ]), "General")
                tabs.addTab(_form_tab(QFormLayout, QWidget, [
                    ("Provider", self.provider),
                    ("OpenAI-compatible base URL", self.openai_base_url),
                    ("OpenAI-compatible model", self.openai_model),
                    ("OpenAI-compatible API key", self.openai_api_key),
                    ("Ollama base URL", self.ollama_base_url),
                    ("Ollama model", self.ollama_model),
                ]), "Model")
                tabs.addTab(_form_tab(QFormLayout, QWidget, [
                    ("Rime user directory", self.rime_dir),
                    ("Schema", self.rime_schema),
                    ("Generated dictionary", self.rime_dictionary),
                    ("Base dictionary", self.rime_base_dictionary),
                ]), "Rime")

                buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
                buttons.accepted.connect(self.accept)
                buttons.rejected.connect(self.reject)
                layout = QVBoxLayout()
                layout.addWidget(tabs)
                layout.addWidget(buttons)
                self.setLayout(layout)

            def to_settings(self) -> AppSettings:
                return AppSettings(
                    listener_enabled=self.listener_enabled.isChecked(),
                    record_full_keylog=self.record_full_keylog.isChecked(),
                    send_full_keylog=self.send_full_keylog.isChecked(),
                    start_on_login=self.start_on_login.isChecked(),
                    provider=self.provider.currentText(),
                    openai_base_url=self.openai_base_url.text().strip(),
                    openai_model=self.openai_model.text().strip() or "gpt-5.4-mini",
                    openai_api_key_env="AI_IME_OPENAI_API_KEY",
                    ollama_base_url=self.ollama_base_url.text().strip() or "http://localhost:11434",
                    ollama_model=self.ollama_model.text().strip(),
                    rime_dir=self.rime_dir.text().strip(),
                    rime_schema=self.rime_schema.text().strip() or "luna_pinyin",
                    rime_dictionary=self.rime_dictionary.text().strip() or "ai_typo",
                    rime_base_dictionary=self.rime_base_dictionary.text().strip() or "luna_pinyin",
                    keylog_file=self.keylog_file.text().strip(),
                )

            def api_key(self) -> str:
                return self.openai_api_key.text()

        return _Dialog(settings)


def _form_tab(QFormLayout: Any, QWidget: Any, rows: list[tuple[str, Any]]) -> Any:
    widget = QWidget()
    layout = QFormLayout()
    for label, field in rows:
        layout.addRow(label, field)
    widget.setLayout(layout)
    return widget


if __name__ == "__main__":
    raise SystemExit(main())
