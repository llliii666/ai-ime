from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_ime.shortcut import build_shortcut_spec, create_desktop_shortcut


class ShortcutTests(unittest.TestCase):
    def test_build_shortcut_spec_prefers_project_pythonw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            desktop = Path(tmp) / "Desktop"
            pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
            pythonw.parent.mkdir(parents=True)
            pythonw.touch()
            root.mkdir(exist_ok=True)

            spec = build_shortcut_spec(project_root=root, desktop_dir=desktop)

            self.assertEqual(spec.path, desktop / "AI IME.lnk")
            self.assertEqual(spec.target, pythonw)
            self.assertEqual(spec.arguments, "-m ai_ime.app")
            self.assertEqual(spec.working_directory, root)
            self.assertEqual(spec.icon_location, f"{pythonw},0")

    def test_build_shortcut_spec_accepts_custom_path_and_name_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            target = root / ".venv" / "Scripts" / "python.exe"
            custom = Path(tmp) / "custom" / "Start.lnk"
            root.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            target.touch()

            spec = build_shortcut_spec(name="Ignored.lnk", shortcut_path=custom, project_root=root)

            self.assertEqual(spec.path, custom)
            self.assertEqual(spec.target, target)

    def test_create_desktop_shortcut_invokes_powershell_shortcut_writer(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            desktop = Path(tmp) / "Desktop"
            pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
            root.mkdir(parents=True)
            pythonw.parent.mkdir(parents=True)
            pythonw.touch()

            with (
                patch("ai_ime.shortcut.os.name", "nt"),
                patch("ai_ime.shortcut.default_project_root", return_value=root),
                patch("ai_ime.shortcut.default_desktop_dir", return_value=desktop),
                patch("ai_ime.shortcut.subprocess.run", return_value=completed) as run,
            ):
                spec = create_desktop_shortcut()

            self.assertEqual(spec.path, desktop / "AI IME.lnk")
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["powershell", "-NoProfile", "-ExecutionPolicy"])
            self.assertIn("WScript.Shell", command[-1])
            self.assertIn(str(spec.path), command[-1])


if __name__ == "__main__":
    unittest.main()
