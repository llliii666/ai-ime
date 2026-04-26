import unittest

from ai_ime.doctor import CheckResult, format_checks, has_error


class DoctorTests(unittest.TestCase):
    def test_format_checks(self) -> None:
        output = format_checks([CheckResult("env", "OK", "provider mock")])

        self.assertEqual(output, "[OK] env: provider mock")

    def test_has_error(self) -> None:
        self.assertTrue(has_error([CheckResult("keyboard", "ERROR", "missing")]))
        self.assertFalse(has_error([CheckResult("env", "WARN", "missing key")]))


if __name__ == "__main__":
    unittest.main()
