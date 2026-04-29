from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai_ime.config import default_data_dir
from ai_ime.models import LearnedRule
from ai_ime.rime.generator import (
    AI_IME_LUA_BOOTSTRAP_START,
    AI_IME_LUA_PROCESSOR,
    remove_lua_bootstrap,
    render_dictionary,
    render_lua_logger,
    render_lua_processor_patch,
    render_schema_dependency_patch,
    render_schema_patch,
    render_support_schema,
    render_typo_translator_patch,
    validate_rime_identifier,
)

MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class DeploymentResult:
    dictionary_path: Path
    support_schema_path: Path
    patch_path: Path
    lua_path: Path
    rime_lua_path: Path | None
    backup_dir: Path
    patch_applied: bool


def deploy_rime_files(
    rules: list[LearnedRule],
    rime_dir: Path,
    schema_id: str = "rime_ice",
    dictionary_id: str = "ai_typo",
    base_dictionary: str = "",
    force_schema_patch: bool = False,
    semantic_log_path: Path | None = None,
    semantic_logger_enabled: bool = True,
) -> DeploymentResult:
    rime_dir.mkdir(parents=True, exist_ok=True)
    schema_id = validate_rime_identifier(schema_id, "schema")
    dictionary_id = validate_rime_identifier(dictionary_id, "dictionary")
    if base_dictionary.strip():
        validate_rime_identifier(base_dictionary.strip(), "base dictionary")
    backup_dir = _create_backup_dir(rime_dir)
    dictionary_path = _safe_rime_output_path(rime_dir, f"{dictionary_id}.dict.yaml")
    support_schema_path = _safe_rime_output_path(rime_dir, f"{dictionary_id}.schema.yaml")
    patch_path = _safe_rime_output_path(rime_dir, f"{schema_id}.custom.yaml")
    lua_path = _safe_rime_output_path(rime_dir, "lua/ai_ime_logger.lua")
    rime_lua_path = _safe_rime_output_path(rime_dir, "rime.lua")
    log_path = semantic_log_path or default_data_dir() / "keylog.jsonl"

    manifest = {"files": []}
    _backup_target(dictionary_path, backup_dir, manifest, root=rime_dir)

    dictionary_path.write_text(
        render_dictionary(rules, dictionary_id=dictionary_id, base_dictionary=base_dictionary),
        encoding="utf-8",
        newline="\n",
    )
    _backup_target(support_schema_path, backup_dir, manifest, root=rime_dir)
    support_schema_path.write_text(
        render_support_schema(dictionary_id=dictionary_id),
        encoding="utf-8",
        newline="\n",
    )

    patch_content = render_schema_patch(dictionary_id=dictionary_id)
    patch_applied = True
    if patch_path.exists() and not force_schema_patch:
        existing_content = patch_path.read_text(encoding="utf-8-sig")
        merged_content = merge_schema_patch(existing_content, dictionary_id=dictionary_id)
        if existing_content != merged_content:
            _backup_target(patch_path, backup_dir, manifest, root=rime_dir)
            patch_path.write_text(merged_content, encoding="utf-8", newline="\n")
    else:
        _backup_target(patch_path, backup_dir, manifest, root=rime_dir)
        patch_path.write_text(patch_content, encoding="utf-8", newline="\n")

    _backup_target(lua_path, backup_dir, manifest, root=rime_dir)
    lua_path.parent.mkdir(parents=True, exist_ok=True)
    lua_path.write_text(render_lua_logger(log_path, enabled=semantic_logger_enabled), encoding="utf-8", newline="\n")

    legacy_rime_lua_path = _remove_legacy_rime_lua_bootstrap(rime_lua_path, backup_dir, manifest, root=rime_dir)

    _write_manifest(backup_dir, manifest)
    return DeploymentResult(
        dictionary_path=dictionary_path,
        support_schema_path=support_schema_path,
        patch_path=patch_path,
        lua_path=lua_path,
        rime_lua_path=legacy_rime_lua_path,
        backup_dir=backup_dir,
        patch_applied=patch_applied,
    )


def merge_schema_patch(content: str, dictionary_id: str = "ai_typo") -> str:
    dictionary_id = validate_rime_identifier(dictionary_id, "dictionary")
    lines = content.splitlines()
    patch_index = _find_top_level_patch(lines)

    if patch_index is None:
        prefix = content.rstrip()
        if prefix:
            return f"{prefix}\n\npatch:\n{_render_ai_schema_patch_body(dictionary_id=dictionary_id)}"
        return f"patch:\n{_render_ai_schema_patch_body(dictionary_id=dictionary_id)}"

    block_end = _find_top_level_block_end(lines, patch_index)
    patch_body = _patch_body_lines(lines, patch_index + 1, block_end, dictionary_id=dictionary_id)

    insert_at = patch_index + 1
    lines[insert_at:block_end] = _render_ai_schema_patch_body(dictionary_id=dictionary_id).rstrip().splitlines() + patch_body
    return "\n".join(lines).rstrip() + "\n"


def rollback_backup(rime_dir: Path, backup_dir: Path) -> list[Path]:
    manifest_path = backup_dir / MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"Backup manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[Path] = []
    for item in manifest["files"]:
        target = rime_dir / item["relative_path"]
        if item["existed"]:
            backup_file = backup_dir / item["backup_name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, target)
            restored.append(target)
        elif target.exists():
            target.unlink()
            restored.append(target)
    return restored


def _create_backup_dir(rime_dir: Path) -> Path:
    root = rime_dir / ".ai-ime-backups"
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = root / timestamp
    suffix = 1
    while backup_dir.exists():
        backup_dir = root / f"{timestamp}-{suffix}"
        suffix += 1
    backup_dir.mkdir()
    return backup_dir


def _find_top_level_patch(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.startswith((" ", "\t")):
            continue
        if line.strip() == "patch:":
            return index
    return None


def _find_top_level_block_end(lines: list[str], start_index: int) -> int:
    for index in range(start_index + 1, len(lines)):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            return index
    return len(lines)


def _patch_body_lines(lines: list[str], start_index: int, end_index: int, dictionary_id: str) -> list[str]:
    body: list[str] = []
    index = start_index
    while index < end_index:
        line = lines[index]
        if _is_legacy_dictionary_override(line, dictionary_id=dictionary_id):
            index += 1
            continue
        if _is_schema_dependency_insert(line, dictionary_id=dictionary_id):
            index += 1
            continue
        if _is_typo_translator_insert(line, dictionary_id=dictionary_id):
            index += 1
            continue
        if _is_lua_processor_insert(line):
            index += 1
            continue
        if _is_typo_translator_block(line, dictionary_id=dictionary_id):
            index = _skip_indented_block(lines, index + 1, end_index)
            continue
        body.append(line)
        index += 1
    return body


def _is_legacy_dictionary_override(line: str, dictionary_id: str) -> bool:
    pattern = re.compile(rf"^\s*translator/dictionary\s*:\s*{re.escape(dictionary_id)}\s*(?:#.*)?$")
    return bool(pattern.match(line))


def _is_typo_translator_insert(line: str, dictionary_id: str) -> bool:
    pattern = re.compile(rf"^\s*engine/translators/@[^:]+:\s*table_translator@{re.escape(dictionary_id)}\s*(?:#.*)?$")
    return bool(pattern.match(line))


def _is_lua_processor_insert(line: str) -> bool:
    pattern = re.compile(rf"^\s*engine/processors/@[^:]+:\s*lua_processor@{re.escape(AI_IME_LUA_PROCESSOR)}\s*(?:#.*)?$")
    return bool(pattern.match(line))


def _is_schema_dependency_insert(line: str, dictionary_id: str) -> bool:
    pattern = re.compile(rf"^\s*schema/dependencies/@[^:]+:\s*{re.escape(dictionary_id)}\s*(?:#.*)?$")
    return bool(pattern.match(line))


def _is_typo_translator_block(line: str, dictionary_id: str) -> bool:
    return bool(re.match(rf"^\s{{2}}{re.escape(dictionary_id)}\s*:\s*(?:#.*)?$", line))


def _skip_indented_block(lines: list[str], start_index: int, end_index: int) -> int:
    index = start_index
    while index < end_index:
        line = lines[index]
        if line.strip() and not line.startswith(("    ", "\t")):
            break
        index += 1
    return index


def _backup_target(
    target: Path,
    backup_dir: Path,
    manifest: dict[str, list[dict[str, object]]],
    root: Path | None = None,
) -> None:
    try:
        relative_path = target.relative_to(root or target.parent).as_posix()
    except ValueError:
        relative_path = target.name
    backup_name = relative_path.replace("/", "__").replace("\\", "__")
    existed = target.exists()
    if existed:
        shutil.copy2(target, backup_dir / backup_name)
    manifest["files"].append(
        {
            "relative_path": relative_path,
            "backup_name": backup_name,
            "existed": existed,
        }
    )


def _write_manifest(backup_dir: Path, manifest: dict[str, list[dict[str, object]]]) -> None:
    (backup_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def _safe_rime_output_path(rime_dir: Path, relative_path: str) -> Path:
    root = rime_dir.resolve()
    path = (rime_dir / relative_path).resolve()
    if path.parent != root and root not in path.parents:
        raise ValueError(f"Resolved Rime output path escapes user directory: {relative_path}")
    return path


def _render_ai_schema_patch_body(dictionary_id: str) -> str:
    return (
        render_schema_dependency_patch(dictionary_id=dictionary_id)
        + render_lua_processor_patch()
        + render_typo_translator_patch(dictionary_id=dictionary_id)
    )


def _remove_legacy_rime_lua_bootstrap(
    rime_lua_path: Path,
    backup_dir: Path,
    manifest: dict[str, list[dict[str, object]]],
    root: Path,
) -> Path | None:
    if not rime_lua_path.exists():
        return None
    existing = rime_lua_path.read_text(encoding="utf-8-sig")
    if AI_IME_LUA_BOOTSTRAP_START not in existing:
        return None
    cleaned = remove_lua_bootstrap(existing)
    if existing == cleaned:
        return None
    _backup_target(rime_lua_path, backup_dir, manifest, root=root)
    if cleaned.strip():
        rime_lua_path.write_text(cleaned, encoding="utf-8", newline="\n")
    else:
        rime_lua_path.unlink()
    return rime_lua_path
