from __future__ import annotations

import os
import subprocess
from pathlib import Path


def candidate_weasel_deployers() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name)
        if root:
            candidates.extend(Path(root).glob("Rime/weasel-*/WeaselDeployer.exe"))
            candidates.append(Path(root) / "Rime" / "WeaselDeployer.exe")
    return _dedupe(candidates)


def find_weasel_deployer() -> Path | None:
    for candidate in candidate_weasel_deployers():
        if candidate.exists():
            return candidate
    return None


def run_weasel_deployer(deployer: Path | None = None, timeout: float = 30.0) -> bool:
    executable = deployer or find_weasel_deployer()
    if executable is None:
        return False
    try:
        completed = subprocess.run(
            [str(executable), "/deploy"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return False
    return completed.returncode == 0


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique
