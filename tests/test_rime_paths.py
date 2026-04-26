import tempfile
import unittest
from pathlib import Path

from ai_ime.rime.paths import detect_active_schema


class RimePathsTests(unittest.TestCase):
    def test_detect_active_schema_from_default_custom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            (rime_dir / "default.custom.yaml").write_text(
                "patch:\n  schema_list:\n    - {schema: rime_ice}\n",
                encoding="utf-8",
            )

            self.assertEqual(detect_active_schema(rime_dir), "rime_ice")

    def test_detect_active_schema_from_block_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            (rime_dir / "default.yaml").write_text(
                "schema_list:\n  - schema: luna_pinyin\n",
                encoding="utf-8",
            )

            self.assertEqual(detect_active_schema(rime_dir), "luna_pinyin")


if __name__ == "__main__":
    unittest.main()
