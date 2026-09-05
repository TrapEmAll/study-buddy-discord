"""Run Study Buddy and restart it after pulling new commits from GitHub.

Usage:
    python update_and_restart.py

The process running this file is the watchdog; the Discord bot runs as a child
process so an update can be applied without losing the watchdog itself.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

CHECK_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "300"))
BRANCH = os.getenv("UPDATE_BRANCH", "main")
ROOT = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("study-buddy-watchdog")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=check
    )


def update() -> bool:
    """Fetch and fast-forward the checkout. Return whether new code arrived."""
    status = git("status", "--porcelain").stdout.strip()
    if status:
        logger.error("Local changes detected; refusing to update until the checkout is clean")
        return False

    fetched = git("fetch", "origin", BRANCH, check=False)
    if fetched.returncode:
        logger.warning("GitHub fetch failed: %s", fetched.stderr.strip())
        return False

    current = git("rev-parse", "HEAD").stdout.strip()
    remote = git("rev-parse", f"origin/{BRANCH}").stdout.strip()
    if current == remote:
        return False

    pulled = git("merge", "--ff-only", f"origin/{BRANCH}", check=False)
    if pulled.returncode:
        logger.error("Could not fast-forward to origin/%s: %s", BRANCH, pulled.stderr.strip())
        return False

    logger.info("Updated from %s to %s", current[:12], remote[:12])
    return True


def install_dependencies() -> bool:
    command = [sys.executable, "-m", "pip", "install", "-e", "."]
    result = subprocess.run(command, cwd=ROOT, text=True)
    if result.returncode:
        logger.error("Dependency installation failed")
        return False
    return True


def start_bot() -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-m", "study_buddy"], cwd=ROOT)


def main() -> int:
    child: subprocess.Popen[str] | None = None
    try:
        while True:
            changed = update()
            if changed and not install_dependencies():
                logger.error("Keeping the current bot stopped until dependencies can be installed")
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            if child is None or child.poll() is not None:
                if child is not None:
                    logger.warning("Bot exited with code %s; restarting", child.returncode)
                child = start_bot()
                logger.info("Started bot process %s", child.pid)

            time.sleep(CHECK_INTERVAL_SECONDS)
            if update():
                logger.info("Restarting bot after GitHub update")
                child.terminate()
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    logger.warning("Bot did not stop gracefully; terminating it")
                    child.kill()
                if not install_dependencies():
                    continue
                child = start_bot()
                logger.info("Started updated bot process %s", child.pid)
    except KeyboardInterrupt:
        logger.info("Stopping watchdog")
        if child and child.poll() is None:
            child.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
