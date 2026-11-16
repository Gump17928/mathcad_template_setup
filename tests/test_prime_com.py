"""Tests for the Prime COM wrapper's opening logic, using a stand-in for Prime (no Prime needed)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tool"))

import prime_com  # noqa: E402


class FakeApp:
    """Answers Open() with None `empty_answers` times (Prime still starting, or a bad file), then a worksheet."""

    def __init__(self, empty_answers: int):
        self.empty_answers = empty_answers
        self.opened_paths: list[str] = []

    def Open(self, path: str):  # noqa: N802 - COM method name
        self.opened_paths.append(path)
        if self.empty_answers > 0:
            self.empty_answers -= 1
            return None
        return "worksheet"


@mock.patch.object(prime_com, "OPEN_RETRY_SECONDS", 0)
class OpenWorksheetTest(unittest.TestCase):
    def test_a_slow_start_is_retried_until_prime_answers(self):
        app = FakeApp(empty_answers=2)
        self.assertEqual(prime_com.PrimeSession(app)._open(Path("a.mcdx")), "worksheet")
        self.assertEqual(len(app.opened_paths), 3)

    def test_a_file_prime_never_opens_is_reported_after_the_last_attempt(self):
        app = FakeApp(empty_answers=99)
        with self.assertRaisesRegex(prime_com.PrimeError, "could not open a.mcdx"), \
                prime_com.PrimeSession(app).open_worksheet(Path("a.mcdx")):
            pass
        self.assertEqual(len(app.opened_paths), prime_com.OPEN_ATTEMPTS)

    def test_the_path_is_sent_to_prime_in_long_resolved_form(self):
        app = FakeApp(empty_answers=0)
        path = Path("some") / ".." / "a.mcdx"
        prime_com.PrimeSession(app)._open(path)
        self.assertEqual(app.opened_paths, [str(path.resolve())])


if __name__ == "__main__":
    unittest.main()
