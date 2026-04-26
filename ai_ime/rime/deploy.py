from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai_ime.models import LearnedRule
from ai_ime.rime.generator import render_dictionary, render_schema_patch


MANIFEST_FILE = "manifest.json"


@dataclass(frozen=True)
class DeploymentResult:
    dictionary_path: Path
    patch_path: Path
    backup_dir: Path
    patch_applied: bool


def deploy_rime_files(
    rules: list[LearnedRule],
    rime_dir: Path,
    schema_id: str = "luna_pinyin",
    dictionary_id: str = "ai_typo",
    base_dictionary: str = "luna_pinyin",
    force_schema_patch: bool = False,
) -> DeploymentResult:
    rime_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = _create_backup_dir(rime_dir)
    dictionary_path = rime_dir / f"{dictionary_id}.dict.yaml"
    patch_path = rime_dir / f"{schema_id}.custom.yaml"

    manifest = {"files": []}
    _backup_target(dictionary_path, backup_dir, manifest)

    dictionary_path.write_text(
        render_dictionary(rules, dictionary_id=dictionary_id, base_dictionary=base_dictionary),
        encoding="utf-8",
        newline="\n",
    )

    patch_content = render_schema_patch(dictionary_id=dictionary_id)
    patch_applied = True
    if patch_path.exists() and not force_schema_patch:
        existing_content = patch_path.read_text(encoding="utf-8-sig")
        merged_content = merge_schema_patch(existing_content, dictionary_id=dictionary_id)
        if existing_content != merged_content:
            _backup_target(patch_path, backup_dir, manifest)
            patch_path.write_text(merged_content, encoding="utf-8", newline="\n")
    else:
        _backup_target(patch_path, backup_dir, manifest)
        patch_path.write_text(patch_content, encoding="utf-8", newline="\n")

    _write_manifest(backup_dir, manifest)
    return DeploymentResult(
        dictionary_path=dictionary_path,
        patch_path=patch_path,
        backup_dir=backup_dir,
        patch_applied=patch_applied,
    )


def merge_schema_patch(content: str, dictionary_id: str = "ai_typo") -> str:
    lines = content.splitlines()
    target_line = f"  translator/dictionary: {dictionary_id}"
    patch_index = _find_top_level_patch(lines)

    if patch_index is None:
        prefix = content.rstrip()
        if prefix:
            return f"{prefix}\n\npatch:\n{target_line}\n"
        return f"patch:\n{target_line}\n"

    block_end = _find_top_level_block_end(lines, patch_index)
    translator_pattern = re.compile(r"^(\s*)translator/dictionary\s*:")
    for index in range(patch_index + 1, block_end):
        if translator_pattern.match(lines[index]):
            indent = translator_pattern.match(lines[index]).group(1)  # type: ignore[union-attr]
            lines[index] = f"{indent}translator/dictionary: {dictionary_id}"
            return "\n".join(lines).rstrip() + "\n"

    insert_at = patch_index + 1
    lines.insert(insert_at, target_line)
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


def _backup_target(target: Path, backup_dir: Path, manifest: dict[str, list[dict[str, object]]]) -> None:
    relative_path = target.name
    backup_name = target.name
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
