from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Goal:
    user_id: int
    minutes: int
    day: str


@dataclass(frozen=True)
class Stats:
    total_minutes: int
    today_minutes: int
    weekly_minutes: int
    streak: int
    goal_minutes: int


class StudyService:
    """Persistence and business rules independent of Discord."""

    def __init__(self, database: str | Path = "study_buddy.sqlite3") -> None:
        self.db = sqlite3.connect(str(database))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL, subject TEXT, minutes INTEGER NOT NULL,
                started_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS goals (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,
                day TEXT NOT NULL, minutes INTEGER NOT NULL, PRIMARY KEY(user_id, guild_id, day));
            CREATE TABLE IF NOT EXISTS checkins (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL, plan TEXT NOT NULL, completed INTEGER, created_at TEXT NOT NULL);
        """)
        self.db.commit()

    @staticmethod
    def _day(at: datetime | None = None) -> str:
        return (at or datetime.now(timezone.utc)).date().isoformat()

    def close(self) -> None:
        self.db.close()

    def log(self, user_id: int, guild_id: int, minutes: int, subject: str | None = None,
            at: datetime | None = None) -> None:
        if minutes <= 0 or minutes > 24 * 60:
            raise ValueError("minutes must be between 1 and 1440")
        stamp = (at or datetime.now(timezone.utc)).isoformat()
        self.db.execute("INSERT INTO sessions(user_id,guild_id,subject,minutes,started_at) VALUES(?,?,?,?,?)",
                        (user_id, guild_id, subject, minutes, stamp))
        self.db.commit()

    def set_goal(self, user_id: int, guild_id: int, minutes: int, day: str | None = None) -> Goal:
        if minutes < 0 or minutes > 24 * 60:
            raise ValueError("goal must be between 0 and 1440 minutes")
        target = day or self._day()
        self.db.execute("INSERT INTO goals VALUES(?,?,?,?) ON CONFLICT(user_id,guild_id,day) DO UPDATE SET minutes=excluded.minutes",
                        (user_id, guild_id, target, minutes))
        self.db.commit()
        return Goal(user_id, minutes, target)

    def checkin(self, user_id: int, guild_id: int, plan: str) -> int:
        if not plan.strip() or len(plan) > 500:
            raise ValueError("plan must be 1-500 characters")
        cur = self.db.execute("INSERT INTO checkins(user_id,guild_id,plan,created_at) VALUES(?,?,?,?)",
                              (user_id, guild_id, plan.strip(), datetime.now(timezone.utc).isoformat()))
        self.db.commit()
        return int(cur.lastrowid)

    def review(self, checkin_id: int, user_id: int, completed: bool) -> None:
        cur = self.db.execute("UPDATE checkins SET completed=? WHERE id=? AND user_id=?",
                              (int(completed), checkin_id, user_id))
        if cur.rowcount == 0:
            raise ValueError("check-in not found or not owned by you")
        self.db.commit()

    def _minutes(self, user_id: int, guild_id: int, since: str | None = None) -> int:
        query = "SELECT COALESCE(SUM(minutes),0) FROM sessions WHERE user_id=? AND guild_id=?"
        args: list[object] = [user_id, guild_id]
        if since:
            query += " AND started_at >= ?"
            args.append(since)
        return int(self.db.execute(query, args).fetchone()[0])

    def streak(self, user_id: int, guild_id: int, today: date | None = None) -> int:
        rows = self.db.execute("SELECT DISTINCT substr(started_at,1,10) day FROM sessions WHERE user_id=? AND guild_id=? ORDER BY day DESC",
                               (user_id, guild_id)).fetchall()
        expected = today or datetime.now(timezone.utc).date()
        days = {date.fromisoformat(row[0]) for row in rows}
        if expected not in days:
            expected -= timedelta(days=1)
        count = 0
        while expected in days:
            count += 1
            expected -= timedelta(days=1)
        return count

    def stats(self, user_id: int, guild_id: int, now: datetime | None = None) -> Stats:
        current = now or datetime.now(timezone.utc)
        today = current.date().isoformat()
        week = (current.date() - timedelta(days=6)).isoformat()
        goal = self.db.execute("SELECT minutes FROM goals WHERE user_id=? AND guild_id=? AND day=?",
                               (user_id, guild_id, today)).fetchone()
        return Stats(self._minutes(user_id, guild_id), self._minutes(user_id, guild_id, today),
                     self._minutes(user_id, guild_id, week), self.streak(user_id, guild_id, current.date()),
                     int(goal[0]) if goal else 0)

    def leaderboard(self, guild_id: int, limit: int = 10, now: datetime | None = None) -> list[tuple[int, int]]:
        since = ((now or datetime.now(timezone.utc)).date() - timedelta(days=6)).isoformat()
        rows = self.db.execute("SELECT user_id,SUM(minutes) total FROM sessions WHERE guild_id=? AND started_at>=? GROUP BY user_id ORDER BY total DESC LIMIT ?",
                               (guild_id, since, limit)).fetchall()
        return [(int(row[0]), int(row[1])) for row in rows]
