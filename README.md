# Study Buddy

A Discord study companion with Pomodoro timers, study logging, goals, streaks, leaderboards, check-ins, reminders, and temporary focus rooms.

## Features

- Slash commands: `/start`, `/break`, `/session`, `/log`, `/stats`, `/streak`, `/goal`, `/checkin`, `/review`, and `/focus-room`.
- Persistent SQLite storage for sessions, goals, check-ins, and achievements.
- Daily goals, streak tracking, weekly leaderboard, and achievement roles.
- Automatic timer completion and optional reminder messages.
- Temporary focus voice channels when the bot has `Manage Channels` permission; empty rooms are cleaned up automatically.
- Pure Python service layer with unit tests; Discord integration is a thin adapter.

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate        # Windows
pip install -e ".[dev]"
python -m study_buddy
```

Set `DISCORD_TOKEN` before starting. Optional `STUDY_BUDDY_DB` selects the SQLite path (default: `study_buddy.sqlite3`).

## Development

```bash
python -m unittest discover -s tests -v
```

The bot requires Discord permissions to send messages, create/manage channels, and use slash commands. Configure `DISCORD_GUILD_ID` to sync commands immediately to one development server; omit it for global command sync.
