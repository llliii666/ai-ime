import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_ime.startup import APP_RUN_NAME, RUN_KEY, default_startup_command, sync_start_on_login


class FakeKey:
    def __init__(self, registry: "FakeWinreg") -> None:
        self.registry = registry

    def __enter__(self) -> "FakeKey":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 1
    KEY_READ = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def CreateKeyEx(self, root: object, path: str, reserved: int, access: int) -> FakeKey:
        self.created_path = path
        return FakeKey(self)

    def OpenKey(self, root: object, path: str, reserved: int, access: int) -> FakeKey:
        self.opened_path = path
        if path != RUN_KEY:
            raise FileNotFoundError(path)
        return FakeKey(self)

    def SetValueEx(self, key: FakeKey, name: str, reserved: int, value_type: int, value: str) -> None:
        self.values[name] = value

    def QueryValueEx(self, key: FakeKey, name: str) -> tuple[str, int]:
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def DeleteValue(self, key: FakeKey, name: str) -> None:
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]

    def FlushKey(self, key: FakeKey) -> None:
        return None


class StartupTests(unittest.TestCase):
    def test_default_startup_command_uses_source_launcher_script(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            launcher = root / "run.py"
            launcher.write_text("from ai_ime.app import main\n", encoding="utf-8")
            pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
            pythonw.parent.mkdir(parents=True)
            pythonw.touch()

            command = default_startup_command(project_root=root)

        self.assertIn(str(pythonw), command)
        self.assertIn(str(launcher), command)
        self.assertNotIn("-m ai_ime.tray", command)

    def test_default_startup_command_falls_back_to_app_module(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            python = root / "python.exe"
            python.touch()

            command = default_startup_command(project_root=root, python_executable=python)

        self.assertIn(str(python), command)
        self.assertIn("-m ai_ime.app", command)

    def test_default_startup_command_uses_foreground_for_frozen_exe(self) -> None:
        with patch("ai_ime.startup.sys.frozen", True, create=True), patch(
            "ai_ime.startup.sys.executable", r"C:\Program Files\AI IME\AI IME.exe"
        ):
            command = default_startup_command()

        self.assertEqual(command, '"C:\\Program Files\\AI IME\\AI IME.exe" --foreground')

    def test_sync_start_on_login_creates_updates_and_deletes_run_value(self) -> None:
        fake_winreg = FakeWinreg()
        with TemporaryDirectory() as tmp, patch.dict("sys.modules", {"winreg": fake_winreg}), patch(
            "ai_ime.startup.os.name", "nt"
        ):
            root = Path(tmp) / "project"
            root.mkdir()
            launcher = root / "run.py"
            launcher.touch()
            python = root / "pythonw.exe"
            python.touch()
            expected = default_startup_command(project_root=root, python_executable=python)
            with patch("ai_ime.startup.default_startup_command", return_value=expected):
                enabled = sync_start_on_login(True)
                fake_winreg.values[APP_RUN_NAME] = "stale"
                repaired = sync_start_on_login(True)
                disabled = sync_start_on_login(False)

        self.assertTrue(enabled)
        self.assertTrue(repaired)
        self.assertFalse(disabled)
        self.assertNotIn(APP_RUN_NAME, fake_winreg.values)


if __name__ == "__main__":
    unittest.main()
