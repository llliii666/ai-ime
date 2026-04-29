from __future__ import annotations

import os
import subprocess
from pathlib import Path


def candidate_weasel_deployers() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("AI_IME_WEASEL_DEPLOYER")
    if configured:
        candidates.append(Path(configured))
    candidates.extend(_running_weasel_deployer_candidates())
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


def _running_weasel_deployer_candidates() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process WeaselServer -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path",
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []

    candidates: list[Path] = []
    for line in completed.stdout.splitlines():
        server_path = Path(line.strip())
        if server_path.name.lower() == "weaselserver.exe":
            candidates.append(server_path.with_name("WeaselDeployer.exe"))
    return candidates


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
