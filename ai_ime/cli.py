from __future__ import annotations

import argparse
from pathlib import Path

from .config import default_db_path
from .correction.normalize import normalize_pinyin
from .correction.rules import aggregate_rules
from .db import connect, init_db, insert_event, list_events, list_rules, upsert_rules
from .models import CorrectionEvent
from .providers import MockProvider, OllamaProvider, OpenAICompatibleProvider, ProviderError
from .rime.deploy import deploy_rime_files, rollback_backup
from .rime.generator import export_rime_files
from .rime.paths import find_existing_user_dir


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return int(args.handler(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-ime", description="Personal pinyin typo learning helper.")
    parser.add_argument("--db", type=Path, default=default_db_path(), help="SQLite database path.")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-db", help="Create or migrate the SQLite database.")
    init_parser.set_defaults(handler=handle_init_db)

    add_parser = subparsers.add_parser("add-event", help="Add one correction event.")
    add_parser.add_argument("--wrong", required=True, help="Mistyped pinyin, e.g. xainzai.")
    add_parser.add_argument("--correct", required=True, help="Correct pinyin, e.g. xianzai.")
    add_parser.add_argument("--text", required=True, help="Committed text, e.g. 现在.")
    add_parser.add_argument("--commit-key", default="unknown", help="Confirm key, e.g. space or enter.")
    add_parser.add_argument("--source", default="manual", help="Event source.")
    add_parser.set_defaults(handler=handle_add_event)

    analyze_parser = subparsers.add_parser("analyze", help="Aggregate events into learned rules.")
    analyze_parser.add_argument("--min-count", type=int, default=1, help="Minimum observations per rule.")
    analyze_parser.set_defaults(handler=handle_analyze)

    analyze_ai_parser = subparsers.add_parser("analyze-ai", help="Analyze events with an AI provider.")
    analyze_ai_parser.add_argument(
        "--provider",
        choices=["mock", "ollama", "openai-compatible"],
        default="mock",
        help="AI provider to use.",
    )
    analyze_ai_parser.add_argument("--model", default="", help="Model name for ollama/openai-compatible.")
    analyze_ai_parser.add_argument("--base-url", default="", help="Provider base URL.")
    analyze_ai_parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Env var containing API key.")
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

    export_parser = subparsers.add_parser("export-rime", help="Export Rime dictionary and schema patch files.")
    export_parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    export_parser.add_argument("--schema", default="luna_pinyin", help="Rime schema id to patch.")
    export_parser.add_argument("--dictionary", default="ai_typo", help="Generated dictionary id.")
    export_parser.add_argument("--base-dictionary", default="luna_pinyin", help="Base Rime dictionary to import.")
    export_parser.set_defaults(handler=handle_export_rime)

    deploy_parser = subparsers.add_parser("deploy-rime", help="Safely deploy generated Rime files.")
    deploy_parser.add_argument("--rime-dir", type=Path, help="Rime user data directory. Auto-detected if omitted.")
    deploy_parser.add_argument("--schema", default="luna_pinyin", help="Rime schema id to patch.")
    deploy_parser.add_argument("--dictionary", default="ai_typo", help="Generated dictionary id.")
    deploy_parser.add_argument("--base-dictionary", default="luna_pinyin", help="Base Rime dictionary to import.")
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
            f"[{enabled}] {rule.wrong_pinyin} -> {rule.correct_pinyin} -> {rule.committed_text} "
            f"confidence={rule.confidence:.3f} weight={rule.weight} count={rule.count} type={rule.mistake_type}"
        )
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
            model=args.model,
            base_url=args.base_url or "http://localhost:11434",
            timeout=args.timeout,
        )
    if args.provider == "openai-compatible":
        return OpenAICompatibleProvider(
            model=args.model,
            base_url=args.base_url or "https://api.openai.com/v1",
            api_key_env=args.api_key_env,
            timeout=args.timeout,
            use_json_mode=not args.no_json_mode,
        )
    raise ValueError(f"Unsupported provider: {args.provider}")
