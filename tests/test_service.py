import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from study_buddy.service import StudyService


class StudyServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.temp.close()
        self.service = StudyService(self.temp.name)

    def tearDown(self):
        self.service.close()

    def test_logging_and_stats(self):
        now = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        self.service.set_goal(1, 2, 60, "2026-09-05")
        self.service.log(1, 2, 25, "Math", now)
        self.service.log(1, 2, 20, "Math", now)
        stats = self.service.stats(1, 2, now)
        self.assertEqual((stats.today_minutes, stats.weekly_minutes, stats.goal_minutes), (45, 45, 60))

    def test_streak_allows_yesterday_start(self):
        now = datetime(2026, 9, 5, tzinfo=timezone.utc)
        self.service.log(1, 2, 10, at=now - timedelta(days=1))
        self.service.log(1, 2, 10, at=now - timedelta(days=2))
        self.assertEqual(self.service.streak(1, 2, now.date()), 2)

    def test_leaderboard_orders_users(self):
        now = datetime(2026, 9, 5, tzinfo=timezone.utc)
        self.service.log(1, 2, 10, at=now)
        self.service.log(2, 2, 30, at=now)
        self.assertEqual(self.service.leaderboard(2, now=now), [(2, 30), (1, 10)])

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            self.service.log(1, 2, 0)
        with self.assertRaises(ValueError):
            self.service.checkin(1, 2, " ")


if __name__ == "__main__":
    unittest.main()
