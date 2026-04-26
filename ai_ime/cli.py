from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import default_db_path, env_value, load_env_file
from .correction.detector import detect_from_sequence
from .correction.normalize import normalize_pinyin
from .correction.rules import aggregate_rules
from .db import (
    clear_events,
    connect,
    delete_rule,
    init_db,
    insert_event,
    list_events,
    list_rules,
    set_rule_enabled,
    upsert_rules,
)
from .doctor import format_checks, has_error, run_checks
from .listener import ListenerError, keylog_to_sequence, run_keyboard_listener
from .models import CorrectionEvent
from .providers import MockProvider, OllamaProvider, OpenAICompatibleProvider, ProviderError
from .rime.deploy import deploy_rime_files, rollback_backup
from .rime.generator import export_rime_files
from .rime.paths import find_existing_user_dir


def main(argv: list[str] | None = None) -> int:
    load_env_file(Path(".env"))
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.env_file != Path(".env"):
        load_env_file(args.env_file, override=True)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return int(args.handler(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-ime", description="Personal pinyin typo learning helper.")
    parser.add_argument("--db", type=Path, default=default_db_path(), help="SQLite database path.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Optional env file path.")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-db", help="Create or migrate the SQLite database.")
    init_parser.set_defaults(handler=handle_init_db)

    doctor_parser = subparsers.add_parser("doctor", help="Check local AI IME environment.")
    doctor_parser.set_defaults(handler=handle_doctor)

    add_parser = subparsers.add_parser("add-event", help="Add one correction event.")
    add_parser.add_argument("--wrong", required=True, help="Mistyped pinyin, e.g. xainzai.")
    add_parser.add_argument("--correct", required=True, help="Correct pinyin, e.g. xianzai.")
    add_parser.add_argument("--text", required=True, help="Committed text, e.g. 现在.")
    add_parser.add_argument("--commit-key", default="unknown", help="Confirm key, e.g. space or enter.")
    add_parser.add_argument("--source", default="manual", help="Event source.")
    add_parser.set_defaults(handler=handle_add_event)

    events_parser = subparsers.add_parser("list-events", help="List correction events.")
    events_parser.add_argument("--limit", type=int, help="Maximum number of events to show.")
    events_parser.set_defaults(handler=handle_list_events)

    clear_events_parser = subparsers.add_parser("clear-events", help="Delete all correction events.")
    clear_events_parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
    clear_events_parser.set_defaults(handler=handle_clear_events)

    detect_parser = subparsers.add_parser("detect-sequence", help="Detect and store one correction from a key sequence.")
    detect_parser.add_argument(
        "--sequence",
        required=True,
        help="Typed sequence, e.g. xainzai{backspace*7}xianzai{space}.",
    )
    detect_parser.add_argument("--text", required=True, help="Committed text.")
    detect_parser.set_defaults(handler=handle_detect_sequence)

    listen_parser = subparsers.add_parser("listen", help="Record explicit local keyboard logs for a limited time.")
    listen_parser.add_argument("--log-file", type=Path, default=Path(".data/keylog.jsonl"), help="JSONL log file.")
    listen_parser.add_argument("--duration", type=float, default=60.0, help="Seconds to listen; 0 means until hotkey.")
    listen_parser.add_argument("--stop-hotkey", default="ctrl+alt+shift+p", help="Hotkey to stop listening.")
    listen_parser.add_argument("--echo", action="store_true", help="Print captured key names while listening.")
    listen_parser.add_argument(
        "--i-understand",
        action="store_true",
        help="Required acknowledgement that this records local keyboard input.",
    )
    listen_parser.set_defaults(handler=handle_listen)

    detect_log_parser = subparsers.add_parser("detect-log", help="Detect one correction from a local keyboard log.")
    detect_log_parser.add_argument("--log-file", type=Path, required=True, help="JSONL keyboard log file.")
    detect_log_parser.add_argument("--text", required=True, help="Committed text to attach to the detected correction.")
    detect_log_parser.set_defaults(handler=handle_detect_log)

    clear_keylog_parser = subparsers.add_parser("clear-keylog", help="Delete a local keyboard log file.")
    clear_keylog_parser.add_argument("--log-file", type=Path, required=True, help="JSONL keyboard log file.")
    clear_keylog_parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
    clear_keylog_parser.set_defaults(handler=handle_clear_keylog)

    analyze_parser = subparsers.add_parser("analyze", help="Aggregate events into learned rules.")
    analyze_parser.add_argument("--min-count", type=int, default=1, help="Minimum observations per rule.")
    analyze_parser.set_defaults(handler=handle_analyze)

    analyze_ai_parser = subparsers.add_parser("analyze-ai", help="Analyze events with an AI provider.")
    analyze_ai_parser.add_argument(
        "--provider",
        choices=["mock", "ollama", "openai-compatible"],
        default=_provider_default(),
        help="AI provider to use.",
    )
    analyze_ai_parser.add_argument("--model", default="", help="Model name for ollama/openai-compatible.")
    analyze_ai_parser.add_argument("--base-url", default="", help="Provider base URL.")
    analyze_ai_parser.add_argument(
        "--api-key-env",
        default=env_value("AI_IME_OPENAI_API_KEY_ENV", default="AI_IME_OPENAI_API_KEY"),
        help="Env var containing API key.",
    )
    analyze_ai_parser.add_argument("--timeout", type=float, default=60.0, help="Provider timeout in seconds.")
    analyze_ai_parser.add_argument(
        "--no-json-mode",
        action="store_true",
        help="Disable OpenAI-compatible JSON mode for providers that do not support it.",
    )
    analyze_ai_parser.set_defaults(handler=handle_analyze_ai)

    list_rules_parser = subparsers.add_parser("list-rules", help="List learned rules.")
    list_rules_parser.add_argument("--enabled-only", action="store_true", help="Only list enabled rules.")
    list_rules_parser.set_defaults(handler=handle_list_rules)

    enable_rule_parser = subparsers.add_parser("enable-rule", help="Enable a learned rule by id.")
    enable_rule_parser.add_argument("rule_id", type=int, help="Rule id.")
    enable_rule_parser.set_defaults(handler=handle_enable_rule)

    disable_rule_parser = subparsers.add_parser("disable-rule", help="Disable a learned rule by id.")
    disable_rule_parser.add_argument("rule_id", type=int, help="Rule id.")
    disable_rule_parser.set_defaults(handler=handle_disable_rule)

    delete_rule_parser = subparsers.add_parser("delete-rule", help="Delete a learned rule by id.")
    delete_rule_parser.add_argument("rule_id", type=int, help="Rule id.")
    delete_rule_parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
    delete_rule_parser.set_defaults(handler=handle_delete_rule)

    export_parser = subparsers.add_parser("export-rime", help="Export Rime dictionary and schema patch files.")
    export_parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    export_parser.add_argument("--schema", default="luna_pinyin", help="Rime schema id to patch.")
    export_parser.add_argument("--dictionary", default="ai_typo", help="Generated dictionary id.")
    export_parser.add_argument("--base-dictionary", default="", help="Optional base Rime dictionary to import.")
    export_parser.set_defaults(handler=handle_export_rime)

    deploy_parser = subparsers.add_parser("deploy-rime", help="Safely deploy generated Rime files.")
    deploy_parser.add_argument("--rime-dir", type=Path, help="Rime user data directory. Auto-detected if omitted.")
    deploy_parser.add_argument("--schema", default="luna_pinyin", help="Rime schema id to patch.")
    deploy_parser.add_argument("--dictionary", default="ai_typo", help="Generated dictionary id.")
    deploy_parser.add_argument("--base-dictionary", default="", help="Optional base Rime dictionary to import.")
    deploy_parser.add_argument(
        "--force-schema-patch",
        action="store_true",
        help="Overwrite an existing schema patch after backing it up.",
    )
    deploy_parser.set_defaults(handler=handle_deploy_rime)

    rollback_parser = subparsers.add_parser("rollback-rime", help="Rollback a previous deploy-rime backup.")
    rollback_parser.add_argument("--rime-dir", type=Path, help="Rime user data directory. Auto-detected if omitted.")
    rollback_parser.add_argument("--backup", type=Path, required=True, help="Backup directory returned by deploy-rime.")
    rollback_parser.set_defaults(handler=handle_rollback_rime)

    locate_parser = subparsers.add_parser("locate-rime", help="Locate the Rime user data directory.")
    locate_parser.set_defaults(handler=handle_locate_rime)

    return parser


def handle_init_db(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        init_db(conn)
    print(f"Initialized database: {args.db}")
    return 0


def handle_doctor(args: argparse.Namespace) -> int:
    results = run_checks(db_path=args.db)
    print(format_checks(results))
    return 1 if has_error(results) else 0


def handle_add_event(args: argparse.Namespace) -> int:
    event = CorrectionEvent(
        wrong_pinyin=normalize_pinyin(args.wrong),
        correct_pinyin=normalize_pinyin(args.correct),
        committed_text=args.text.strip(),
        commit_key=args.commit_key,
        source=args.source,
    )
    with connect(args.db) as conn:
        init_db(conn)
        event_id = insert_event(conn, event)
    print(f"Added event #{event_id}: {event.wrong_pinyin} -> {event.correct_pinyin} -> {event.committed_text}")
    return 0


def handle_list_events(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        init_db(conn)
        events = list_events(conn, limit=args.limit)
    if not events:
        print("No correction events.")
        return 0
    for event in events:
        print(
            f"#{event.id} {event.wrong_pinyin} -> {event.correct_pinyin} -> {event.committed_text} "
            f"commit={event.commit_key} source={event.source} created={event.created_at}"
        )
    return 0


def handle_clear_events(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to delete events without --yes.")
        return 2
    with connect(args.db) as conn:
        init_db(conn)
        deleted = clear_events(conn)
    print(f"Deleted {deleted} correction event(s).")
    return 0


def handle_detect_sequence(args: argparse.Namespace) -> int:
    event = detect_from_sequence(args.sequence, committed_text=args.text)
    if event is None:
        print("No correction event detected.")
        return 1
    with connect(args.db) as conn:
        init_db(conn)
        event_id = insert_event(conn, event)
    print(f"Detected event #{event_id}: {event.wrong_pinyin} -> {event.correct_pinyin} -> {event.committed_text}")
    return 0


def handle_listen(args: argparse.Namespace) -> int:
    if not args.i_understand:
        print("Refusing to start keyboard logging without --i-understand.")
        return 2
    print(f"Listening for {args.duration} second(s). Stop hotkey: {args.stop_hotkey}. Log: {args.log_file}")
    try:
        captured = run_keyboard_listener(
            log_file=args.log_file,
            duration=args.duration,
            stop_hotkey=args.stop_hotkey,
            echo=args.echo,
        )
    except ListenerError as exc:
        print(f"Keyboard listener failed: {exc}")
        return 1
    print(f"Captured {captured} keyboard event(s).")
    return 0


def handle_detect_log(args: argparse.Namespace) -> int:
    sequence = keylog_to_sequence(args.log_file)
    if not sequence:
        print("No usable key sequence found in log.")
        return 1
    event = detect_from_sequence(sequence, committed_text=args.text)
    if event is None:
        print("No correction event detected.")
        return 1
    with connect(args.db) as conn:
        init_db(conn)
        event_id = insert_event(conn, event)
    print(f"Detected event #{event_id}: {event.wrong_pinyin} -> {event.correct_pinyin} -> {event.committed_text}")
    return 0


def handle_clear_keylog(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to delete keylog without --yes.")
        return 2
    if not args.log_file.exists():
        print("Keylog file does not exist.")
        return 0
    args.log_file.unlink()
    print(f"Deleted keylog: {args.log_file}")
    return 0


def handle_analyze(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        init_db(conn)
        events = list_events(conn)
        rules = aggregate_rules(events, min_count=args.min_count)
        upserted = upsert_rules(conn, rules)
    print(f"Analyzed {len(events)} event(s); upserted {upserted} rule(s).")
    return 0


def handle_analyze_ai(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        init_db(conn)
        events = list_events(conn)
        provider = _build_provider(args)
        try:
            rules = provider.analyze_events(events)
        except ProviderError as exc:
            print(f"AI analysis failed: {exc}")
            return 1
        upserted = upsert_rules(conn, rules)
    print(f"AI analyzed {len(events)} event(s); upserted {upserted} rule(s) from {args.provider}.")
    return 0


def handle_list_rules(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        init_db(conn)
        rules = list_rules(conn, enabled_only=args.enabled_only)
    if not rules:
        print("No learned rules.")
        return 0
    for rule in rules:
        enabled = "on" if rule.enabled else "off"
        print(
            f"#{rule.id} [{enabled}] {rule.wrong_pinyin} -> {rule.correct_pinyin} -> {rule.committed_text} "
            f"confidence={rule.confidence:.3f} weight={rule.weight} count={rule.count} "
            f"type={rule.mistake_type} provider={rule.provider}"
        )
    return 0


def handle_enable_rule(args: argparse.Namespace) -> int:
    return _set_rule_enabled(args, enabled=True)


def handle_disable_rule(args: argparse.Namespace) -> int:
    return _set_rule_enabled(args, enabled=False)


def handle_delete_rule(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to delete rule without --yes.")
        return 2
    with connect(args.db) as conn:
        init_db(conn)
        deleted = delete_rule(conn, args.rule_id)
    if not deleted:
        print(f"Rule #{args.rule_id} was not found.")
        return 1
    print(f"Deleted rule #{args.rule_id}.")
    return 0


def handle_export_rime(args: argparse.Namespace) -> int:
    with connect(args.db) as conn:
        init_db(conn)
        rules = list_rules(conn, enabled_only=True)
    dictionary_path, patch_path = export_rime_files(
        rules,
        output_dir=args.out,
        schema_id=args.schema,
        dictionary_id=args.dictionary,
        base_dictionary=args.base_dictionary,
    )
    print(f"Exported Rime dictionary: {dictionary_path}")
    print(f"Exported Rime schema patch: {patch_path}")
    return 0


def handle_deploy_rime(args: argparse.Namespace) -> int:
    rime_dir = _resolve_rime_dir(args.rime_dir)
    if rime_dir is None:
        print("Rime user data directory was not found. Pass --rime-dir explicitly.")
        return 1
    with connect(args.db) as conn:
        init_db(conn)
        rules = list_rules(conn, enabled_only=True)
    result = deploy_rime_files(
        rules,
        rime_dir=rime_dir,
        schema_id=args.schema,
        dictionary_id=args.dictionary,
        base_dictionary=args.base_dictionary,
        force_schema_patch=args.force_schema_patch,
    )
    print(f"Deployed Rime dictionary: {result.dictionary_path}")
    if result.patch_applied:
        print(f"Deployed Rime schema patch: {result.patch_path}")
    else:
        print(f"Existing schema patch was not overwritten. Pending patch: {result.patch_path}")
    print(f"Backup directory: {result.backup_dir}")
    return 0


def handle_rollback_rime(args: argparse.Namespace) -> int:
    rime_dir = _resolve_rime_dir(args.rime_dir)
    if rime_dir is None:
        print("Rime user data directory was not found. Pass --rime-dir explicitly.")
        return 1
    restored = rollback_backup(rime_dir=rime_dir, backup_dir=args.backup)
    if restored:
        print("Rolled back:")
        for path in restored:
            print(path)
    else:
        print("Nothing to rollback.")
    return 0


def handle_locate_rime(args: argparse.Namespace) -> int:
    user_dir = find_existing_user_dir()
    if user_dir is None:
        print("Rime user data directory was not found.")
        return 1
    print(user_dir)
    return 0


def _resolve_rime_dir(value: Path | None) -> Path | None:
    if value is not None:
        return value
    return find_existing_user_dir()


def _build_provider(args: argparse.Namespace):
    if args.provider == "mock":
        return MockProvider()
    if args.provider == "ollama":
        return OllamaProvider(
            model=args.model or env_value("AI_IME_OLLAMA_MODEL", "AI_IME_AI_MODEL"),
            base_url=args.base_url or env_value("AI_IME_OLLAMA_BASE_URL", default="http://localhost:11434"),
            timeout=args.timeout,
        )
    if args.provider == "openai-compatible":
        return OpenAICompatibleProvider(
            model=args.model or env_value("AI_IME_OPENAI_MODEL", "AI_IME_AI_MODEL", default="gpt-5.4-mini"),
            base_url=args.base_url or env_value("AI_IME_OPENAI_BASE_URL", default="https://api.openai.com/v1"),
            api_key_env=args.api_key_env,
            timeout=args.timeout,
            use_json_mode=not args.no_json_mode,
        )
    raise ValueError(f"Unsupported provider: {args.provider}")


def _set_rule_enabled(args: argparse.Namespace, enabled: bool) -> int:
    with connect(args.db) as conn:
        init_db(conn)
        updated = set_rule_enabled(conn, args.rule_id, enabled=enabled)
    if not updated:
        print(f"Rule #{args.rule_id} was not found.")
        return 1
    state = "enabled" if enabled else "disabled"
    print(f"{state.capitalize()} rule #{args.rule_id}.")
    return 0


def _provider_default() -> str:
    provider = os.environ.get("AI_IME_PROVIDER", "mock")
    if provider in {"mock", "ollama", "openai-compatible"}:
        return provider
    return "mock"
