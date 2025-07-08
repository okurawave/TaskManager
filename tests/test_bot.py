import unittest
from unittest.mock import MagicMock, patch

import task_bot.bot as bot


class TestParseRelativeDueDate(unittest.TestCase):
    def test_today(self):
        result = bot.parse_relative_due_date("today")
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2} 23:59$")

    def test_tomorrow(self):
        result = bot.parse_relative_due_date("tomorrow")
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2} 23:59$")

    def test_ymd(self):
        result = bot.parse_relative_due_date("2025-07-08")
        self.assertEqual(result, "2025-07-08 23:59")

    def test_ymdhm(self):
        result = bot.parse_relative_due_date("2025-07-08 10:00")
        self.assertEqual(result, "2025-07-08 10:00")

    def test_invalid(self):
        result = bot.parse_relative_due_date("notadate")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
