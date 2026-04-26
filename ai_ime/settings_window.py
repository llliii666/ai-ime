from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path

from ai_ime.config import default_data_dir
from ai_ime.ui_api import SettingsApi


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-ime-settings", description="Open the AI IME settings window.")
    parser.add_argument("--debug", action="store_true", help="Open WebView developer tools where supported.")
    parser.add_argument("--smoke", action="store_true", help="Validate settings UI resources without opening a window.")
    args = parser.parse_args(argv)

    html_path = _settings_html_path()
    if args.smoke:
        return 0 if html_path.exists() else 1

    import webview

    api = SettingsApi()
    html = render_settings_html(api)
    window = webview.create_window(
        "AI IME 设置",
        html=html,
        js_api=api,
        width=1120,
        height=760,
        min_size=(940, 660),
        background_color="#f4f6fa",
        text_select=True,
    )
    api.bind_window(window)
    storage_path = default_data_dir() / "webview"
    storage_path.mkdir(parents=True, exist_ok=True)
    webview.start(debug=args.debug, private_mode=False, storage_path=str(storage_path))
    return 0


def _settings_html_path() -> Path:
    return Path(str(resources.files("ai_ime") / "ui" / "settings.html")).resolve()


def render_settings_html(api: SettingsApi) -> str:
    html = _read_ui_resource("settings.html")
    css = _read_ui_resource("settings.css")
    js = _read_ui_resource("settings.js")
    initial_state = json.dumps(api.load_state(), ensure_ascii=False)
    html = html.replace('    <link rel="stylesheet" href="./settings.css" />', f"    <style>\n{css}\n    </style>")
    html = html.replace(
        '    <script src="./settings.js"></script>',
        f'    <script id="initial-state" type="application/json">{_escape_script_json(initial_state)}</script>\n'
        f"    <script>\n{js}\n    </script>",
    )
    return html


def _read_ui_resource(name: str) -> str:
    path = Path(str(resources.files("ai_ime") / "ui" / name))
    return path.read_text(encoding="utf-8")


def _escape_script_json(value: str) -> str:
    return value.replace("</", "<\\/")


if __name__ == "__main__":
    raise SystemExit(main())
