from __future__ import annotations

import getpass
import os
from pathlib import Path


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_config(root: Path, interactive: bool = True) -> dict[str, str]:
    """Load .env, prompting for first-run Discord settings when needed."""
    env_path = root / ".env"
    file_values = _read_env(env_path)
    config = {key: os.environ.get(key, value) for key, value in file_values.items()}
    for key in ("DISCORD_TOKEN", "DISCORD_GUILD_ID", "STUDY_BUDDY_DB"):
        if key in os.environ:
            config[key] = os.environ[key]

    # A blank guild ID is valid (it means global command sync), so only ask
    # for it when the key has never been configured.
    if (not config.get("DISCORD_TOKEN") or "DISCORD_GUILD_ID" not in config) and interactive:
        if not config.get("DISCORD_TOKEN"):
            config["DISCORD_TOKEN"] = getpass.getpass("Discord bot token (input hidden): ").strip()
        if "DISCORD_GUILD_ID" not in config:
            config["DISCORD_GUILD_ID"] = input("Development guild/server ID (optional, press Enter for global sync): ").strip()
        if not config["DISCORD_TOKEN"]:
            raise RuntimeError("A Discord bot token is required")
        _write_env(env_path, config)
    return config


def _write_env(path: Path, config: dict[str, str]) -> None:
    path.write_text("\n".join([
        "# Study Buddy local configuration (do not commit this file)",
        f"DISCORD_TOKEN={config.get('DISCORD_TOKEN', '')}",
        f"DISCORD_GUILD_ID={config.get('DISCORD_GUILD_ID', '')}",
        f"STUDY_BUDDY_DB={config.get('STUDY_BUDDY_DB', 'study_buddy.sqlite3')}",
        "",
    ]), encoding="utf-8")
