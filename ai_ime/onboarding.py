from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from ai_ime.rime.paths import RIME_ICE_SCHEMA_ID, detect_preferred_schema, find_existing_user_dir, has_rime_ice_config
from ai_ime.setup_wizard import run_initial_setup
from ai_ime.shortcut import create_desktop_shortcut

WEASEL_DOWNLOAD_URL = "https://rime.im/download/"
RIME_ICE_URL = "https://github.com/iDvel/rime-ice"
RIME_ICE_VIDEO_SIMPLE = "https://www.bilibili.com/video/BV1J5UnB5Etu/"
RIME_ICE_VIDEO_WINDOWS = "https://www.bilibili.com/video/BV1FioQY8EXD/"
WEASEL_WINGET_ID = "Rime.Weasel"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print("\n== AI IME 首次启动 ==")
    print(f"项目目录：{Path.cwd()}")

    setup = run_initial_setup(env_path=Path(".env"))
    print("\n== 初始化 ==")
    print(f"设置文件：{setup.settings_path}")
    print(f"数据库：{setup.db_path}")
    print(f"模型配置文件：{setup.env_path.resolve()}")
    print("说明：.env 是本机私有保存位置；模型页面保存配置后会自动写入它。")

    print("\n== 小狼毫/Rime ==")
    rime_dir = find_existing_user_dir()
    if rime_dir is None:
        print("未检测到小狼毫/Rime 用户目录。AI IME 可以先启动，但暂时不能改变输入法候选词。")
        print(f"官方下载页：{WEASEL_DOWNLOAD_URL}")
        print(f"雾凇拼音配置：{RIME_ICE_URL}")
        print(f"参考视频 1：{RIME_ICE_VIDEO_SIMPLE}")
        print(f"参考视频 2：{RIME_ICE_VIDEO_WINDOWS}")
        print(f"winget 安装命令：winget install -e --id {WEASEL_WINGET_ID}")
        if args.install_weasel:
            install_weasel_with_winget()
        elif args.open_weasel_download:
            webbrowser.open(WEASEL_DOWNLOAD_URL)
        else:
            print("推荐先安装小狼毫，再安装雾凇拼音，并在小狼毫里选择“雾凇拼音”，之后再运行 START_HERE.cmd。")
    else:
        print(f"已检测到 Rime 用户目录：{rime_dir}")
        if has_rime_ice_config(rime_dir):
            schema = detect_preferred_schema(rime_dir) or RIME_ICE_SCHEMA_ID
            print(f"已检测到雾凇拼音配置，当前将优先部署到方案：{schema}")
        else:
            print("未检测到雾凇拼音 rime_ice 配置。裸小狼毫通常是繁体体验，建议先安装雾凇拼音。")
            print(f"雾凇拼音配置：{RIME_ICE_URL}")
            print(f"参考视频：{RIME_ICE_VIDEO_WINDOWS}")

    if not args.skip_shortcut:
        print("\n== 桌面快捷方式 ==")
        try:
            shortcut_path = Path(args.shortcut_path) if args.shortcut_path else None
            shortcut = create_desktop_shortcut(shortcut_path=shortcut_path)
            print(f"已创建或更新：{shortcut.path}")
        except Exception as exc:
            print(f"创建桌面快捷方式失败：{exc}")

    if not args.no_start:
        print("\n== 启动托盘程序 ==")
        started = start_tray_background()
        if not started:
            return 1
        print("AI IME 已启动。请查看 Windows 右下角通知区域或隐藏图标菜单。")
        print("点击 AI IME 图标可以打开设置界面。")
    else:
        print("\n已跳过启动。之后可以运行：uv run python run.py")

    print("\n== 下一步 ==")
    print("确认小狼毫已选择“雾凇拼音”后，打开托盘设置界面，在“模型”页配置接口，在“输入法”页部署到小狼毫。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI IME first-run onboarding.")
    parser.add_argument("--no-start", action="store_true", help="Prepare the project without starting the tray app.")
    parser.add_argument("--skip-shortcut", action="store_true", help="Do not create a desktop shortcut.")
    parser.add_argument("--shortcut-path", default="", help="Optional explicit .lnk path.")
    parser.add_argument("--install-weasel", action="store_true", help="Install Weasel with winget if Rime is missing.")
    parser.add_argument("--open-weasel-download", action="store_true", help="Open the official Weasel download page if Rime is missing.")
    return parser


def install_weasel_with_winget() -> None:
    if shutil.which("winget") is None:
        print("没有检测到 winget，已打开小狼毫官方下载页。")
        webbrowser.open(WEASEL_DOWNLOAD_URL)
        return
    print("开始通过 winget 安装小狼毫。该步骤会下载外部安装包，并可能弹出系统确认。")
    completed = subprocess.run(["winget", "install", "-e", "--id", WEASEL_WINGET_ID], check=False)
    if completed.returncode != 0:
        print("winget 安装未完成，可以改用官方下载页。")


def start_tray_background() -> bool:
    command = [sys.executable, "run.py"]
    completed = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        print("启动失败。")
        if completed.stdout.strip():
            print(completed.stdout.strip())
        if completed.stderr.strip():
            print(completed.stderr.strip())
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
