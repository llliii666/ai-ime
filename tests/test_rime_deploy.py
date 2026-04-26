import tempfile
import unittest
from pathlib import Path

from ai_ime.models import LearnedRule
from ai_ime.rime.deploy import deploy_rime_files, rollback_backup


def sample_rules() -> list[LearnedRule]:
    return [
        LearnedRule(
            wrong_pinyin="xainzai",
            correct_pinyin="xianzai",
            committed_text="现在",
            confidence=0.8,
            weight=141000,
            count=1,
            mistake_type="adjacent_transposition",
        )
    ]


class RimeDeployTests(unittest.TestCase):
    def test_deploy_writes_files_and_rollback_removes_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            result = deploy_rime_files(sample_rules(), rime_dir)

            self.assertTrue(result.dictionary_path.exists())
            self.assertTrue(result.patch_path.exists())
            self.assertTrue(result.patch_applied)

            restored = rollback_backup(rime_dir, result.backup_dir)
            self.assertIn(result.dictionary_path, restored)
            self.assertFalse(result.dictionary_path.exists())
            self.assertFalse(result.patch_path.exists())

    def test_existing_patch_is_not_overwritten_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            existing_patch = rime_dir / "luna_pinyin.custom.yaml"
            existing_patch.write_text("patch:\n  menu/page_size: 9\n", encoding="utf-8")

            result = deploy_rime_files(sample_rules(), rime_dir)

            self.assertFalse(result.patch_applied)
            self.assertEqual(existing_patch.read_text(encoding="utf-8"), "patch:\n  menu/page_size: 9\n")
            self.assertTrue(result.patch_path.name.endswith(".pending"))


if __name__ == "__main__":
    unittest.main()
