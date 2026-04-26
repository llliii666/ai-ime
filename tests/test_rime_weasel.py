import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai_ime.rime.weasel import run_weasel_deployer


class RimeWeaselTests(unittest.TestCase):
    def test_run_weasel_deployer_returns_false_when_not_found(self) -> None:
        self.assertFalse(run_weasel_deployer(deployer=Path("Z:/missing/WeaselDeployer.exe"), timeout=0.01))

    def test_run_weasel_deployer_calls_deployer_with_deploy_argument(self) -> None:
        completed = Mock(returncode=0)
        with patch("ai_ime.rime.weasel.subprocess.run", return_value=completed) as mocked_run:
            ok = run_weasel_deployer(deployer=Path(__file__), timeout=1)

        self.assertTrue(ok)
        self.assertEqual(mocked_run.call_args.args[0][-1], "/deploy")


if __name__ == "__main__":
    unittest.main()
