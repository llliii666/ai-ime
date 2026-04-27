import unittest
from importlib import resources


class PackageResourceTests(unittest.TestCase):
    def test_settings_ui_resources_are_packaged(self) -> None:
        root = resources.files("ai_ime")

        for name in ("settings.html", "settings.css", "settings.js"):
            with self.subTest(name=name):
                path = root / "ui" / name
                self.assertTrue(path.is_file())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 100)

    def test_app_icon_resources_are_packaged(self) -> None:
        root = resources.files("ai_ime")

        icon = root / "assets" / "app.ico"
        svg = root / "assets" / "app-icon.svg"

        self.assertTrue(icon.is_file())
        self.assertGreater(icon.stat().st_size, 1000)
        self.assertTrue(svg.is_file())
        self.assertIn("viewBox", svg.read_text(encoding="utf-8"))

    def test_package_marks_type_information(self) -> None:
        self.assertTrue((resources.files("ai_ime") / "py.typed").is_file())


if __name__ == "__main__":
    unittest.main()
