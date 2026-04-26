from __future__ import annotations

import shutil
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ai_ime.config import default_data_dir, default_db_path, load_env_file
from ai_ime.db import connect, init_db
from ai_ime.doctor import CheckResult, run_checks
from ai_ime.rime.paths import detect_active_schema, find_existing_user_dir
from ai_ime.settings import AppSettings, default_settings_path, load_app_settings, save_app_settings


ENV_TEMPLATE = """AI_IME_PROVIDER=openai-compatible
AI_IME_PROVIDER_PRESET=openai
AI_IME_OPENAI_BASE_URL=https://api.openai.com/v1
AI_IME_OPENAI_API_KEY=replace-with-your-key
AI_IME_OPENAI_MODEL=gpt-5.4-mini
"""


@dataclass(frozen=True)
class SetupStep:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class SetupResult:
    db_path: Path
    settings_path: Path
    env_path: Path
    steps: list[SetupStep]
    checks: list[CheckResult]

    @property
    def has_error(self) -> bool:
        return any(step.status == "ERROR" for step in self.steps) or any(check.status == "ERROR" for check in self.checks)


def run_initial_setup(
    db_path: Path | None = None,
    env_path: Path = Path(".env"),
    settings_path: Path | None = None,
    provider: str | None = None,
    dry_run: bool = False,
) -> SetupResult:
    resolved_db_path = db_path or default_db_path()
    resolved_settings_path = settings_path or default_settings_path()
    steps: list[SetupStep] = []

    _prepare_env_file(env_path, dry_run=dry_run, steps=steps)
    if env_path.exists():
        load_env_file(env_path, override=True)

    _prepare_database(resolved_db_path, dry_run=dry_run, steps=steps)
    _prepare_settings(
        settings_path=resolved_settings_path,
        provider=provider,
        dry_run=dry_run,
        steps=steps,
    )
    checks = run_checks(db_path=resolved_db_path)
    return SetupResult(
        db_path=resolved_db_path,
        settings_path=resolved_settings_path,
        env_path=env_path,
        steps=steps,
        checks=checks,
    )


def format_setup_result(result: SetupResult) -> str:
    lines = ["AI IME setup"]
    for step in result.steps:
        lines.append(f"[{step.status}] {step.name}: {step.detail}")
    lines.append("")
    lines.append("Environment checks")
    for check in result.checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
    lines.append("")
    lines.extend(
        [
            f"Settings: {result.settings_path}",
            f"Database: {result.db_path}",
            f"Env file: {result.env_path.resolve()}",
            "Next: run `uv run python run.py` to start the tray app.",
        ]
    )
    return "\n".join(lines)


def _prepare_env_file(env_path: Path, dry_run: bool, steps: list[SetupStep]) -> None:
    if env_path.exists():
        steps.append(SetupStep("env", "OK", f"using existing {env_path.resolve()}"))
        return

    template_path = Path(".env.example")
    detail = f"would create {env_path.resolve()}"
    if dry_run:
        steps.append(SetupStep("env", "DRY-RUN", detail))
        return

    env_path.parent.mkdir(parents=True, exist_ok=True)
    if template_path.exists():
        shutil.copyfile(template_path, env_path)
        steps.append(SetupStep("env", "CREATE", f"created from {template_path}"))
    else:
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8", newline="\n")
        steps.append(SetupStep("env", "CREATE", "created default provider template"))


def _prepare_database(db_path: Path, dry_run: bool, steps: list[SetupStep]) -> None:
    if dry_run:
        steps.append(SetupStep("database", "DRY-RUN", f"would initialize {db_path}"))
        return
    with closing(connect(db_path)) as conn:
        init_db(conn)
    steps.append(SetupStep("database", "OK", f"initialized {db_path}"))


def _prepare_settings(
    settings_path: Path,
    provider: str | None,
    dry_run: bool,
    steps: list[SetupStep],
) -> None:
    settings = load_app_settings(settings_path)
    updated = _settings_with_local_defaults(settings, provider=provider)
    if dry_run:
        steps.append(SetupStep("settings", "DRY-RUN", f"would write {settings_path}"))
        return
    save_app_settings(updated, settings_path)
    steps.append(SetupStep("settings", "OK", f"saved {settings_path}"))


def _settings_with_local_defaults(settings: AppSettings, provider: str | None = None) -> AppSettings:
    if provider:
        settings.provider = provider
    if not settings.keylog_file:
        settings.keylog_file = str(default_data_dir() / "keylog.jsonl")
    if not settings.rime_dir:
        detected = find_existing_user_dir()
        if detected is not None:
            settings.rime_dir = str(detected)
    if settings.rime_dir:
        detected_schema = detect_active_schema(Path(settings.rime_dir))
        if detected_schema and settings.rime_schema in {"", "luna_pinyin"}:
            settings.rime_schema = detected_schema
    return settings
