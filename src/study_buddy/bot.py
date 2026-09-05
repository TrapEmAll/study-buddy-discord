from __future__ import annotations

import os
import logging
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .service import StudyService
from .config import load_config

logger = logging.getLogger(__name__)


class StudyBuddy(commands.Bot):
    def __init__(self, service: StudyService) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.service = service
        self.timers: dict[tuple[int, int], int] = {}

    async def setup_hook(self) -> None:
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.timer_loop.start()

    async def close(self) -> None:
        self.timer_loop.cancel()
        self.service.close()
        await super().close()

    @tasks.loop(seconds=15)
    async def timer_loop(self) -> None:
        now = int(datetime.now(timezone.utc).timestamp())
        expired = [(key, end) for key, end in self.timers.items() if end <= now]
        for (user_id, channel_id), _ in expired:
            self.timers.pop((user_id, channel_id), None)
            channel = self.get_channel(channel_id)
            if channel:
                await channel.send(f"<@{user_id}> focus session complete! Log your time with `/log` and take a break.")
        for guild in self.guilds:
            for channel in tuple(guild.voice_channels):
                if channel.name.startswith("Focus · ") and not channel.members:
                    try:
                        await channel.delete(reason="Study Buddy temporary focus room cleanup")
                    except discord.HTTPException:
                        logger.warning("Could not clean up focus room %s", channel.id, exc_info=True)

    @timer_loop.before_loop
    async def before_timer_loop(self) -> None:
        await self.wait_until_ready()


bot: StudyBuddy | None = None


def register_commands(instance: StudyBuddy) -> None:
    @instance.tree.command(description="Start a Pomodoro focus timer")
    @app_commands.describe(minutes="Focus length in minutes")
    async def start(interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 180] = 25) -> None:
        if not interaction.channel_id:
            return await interaction.response.send_message("This command needs a text channel.", ephemeral=True)
        instance.timers[(interaction.user.id, interaction.channel_id)] = int(datetime.now(timezone.utc).timestamp()) + minutes * 60
        await interaction.response.send_message(f"Focus started for {minutes} minutes. Stay focused!")

    @instance.tree.command(description="Start a break timer")
    async def break_(interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 60] = 5) -> None:
        if interaction.channel_id:
            instance.timers[(interaction.user.id, interaction.channel_id)] = int(datetime.now(timezone.utc).timestamp()) + minutes * 60
        await interaction.response.send_message(f"Break started for {minutes} minutes.")

    @instance.tree.command(description="Show your current timer")
    async def session(interaction: discord.Interaction) -> None:
        end = instance.timers.get((interaction.user.id, interaction.channel_id or 0))
        if not end:
            return await interaction.response.send_message("You have no active timer.", ephemeral=True)
        remaining = max(0, end - int(datetime.now(timezone.utc).timestamp()))
        await interaction.response.send_message(f"Your timer has {remaining // 60}m {remaining % 60}s remaining.", ephemeral=True)

    @instance.tree.command(description="Log completed study minutes")
    async def log(interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 1440], subject: str | None = None) -> None:
        instance.service.log(interaction.user.id, interaction.guild_id or 0, minutes, subject)
        await interaction.response.send_message(f"Logged {minutes} minutes" + (f" of {subject}." if subject else "."))

    @instance.tree.command(description="Show your study statistics")
    async def stats(interaction: discord.Interaction) -> None:
        s = instance.service.stats(interaction.user.id, interaction.guild_id or 0)
        await interaction.response.send_message(f"Today: {s.today_minutes}/{s.goal_minutes} min · This week: {s.weekly_minutes} min · Total: {s.total_minutes} min · Streak: {s.streak} days")

    @instance.tree.command(description="Show your current study streak")
    async def streak(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Your current streak is {instance.service.streak(interaction.user.id, interaction.guild_id or 0)} day(s).")

    @instance.tree.command(description="Set today's study goal")
    async def goal(interaction: discord.Interaction, minutes: app_commands.Range[int, 0, 1440]) -> None:
        instance.service.set_goal(interaction.user.id, interaction.guild_id or 0, minutes)
        await interaction.response.send_message(f"Today's goal is {minutes} minutes.")

    @instance.tree.command(description="Check in with your study plan")
    async def checkin(interaction: discord.Interaction, plan: str) -> None:
        checkin_id = instance.service.checkin(interaction.user.id, interaction.guild_id or 0, plan)
        await interaction.response.send_message(f"Check-in #{checkin_id} recorded: {plan}")

    @instance.tree.command(description="Review your latest check-in")
    async def review(interaction: discord.Interaction, checkin_id: int, completed: bool) -> None:
        instance.service.review(checkin_id, interaction.user.id, completed)
        await interaction.response.send_message("Check-in updated.")

    @instance.tree.command(description="Show the weekly study leaderboard")
    async def leaderboard(interaction: discord.Interaction) -> None:
        rows = instance.service.leaderboard(interaction.guild_id or 0)
        text = "\n".join(f"{i}. <@{uid}> — {mins} min" for i, (uid, mins) in enumerate(rows, 1)) or "No study time logged yet."
        await interaction.response.send_message("**Weekly leaderboard**\n" + text)

    @instance.tree.command(name="focus-room", description="Create a temporary silent study voice room")
    async def focus_room(interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        channel = await interaction.guild.create_voice_channel(f"Focus · {interaction.user.display_name}")
        await interaction.response.send_message(f"Focus room created: {channel.mention}")


def create_bot() -> StudyBuddy:
    service = StudyService(os.getenv("STUDY_BUDDY_DB", "study_buddy.sqlite3"))
    instance = StudyBuddy(service)
    register_commands(instance)
    return instance


def main() -> None:
    config = load_config(Path(__file__).resolve().parents[2])
    for key in ("STUDY_BUDDY_DB", "DISCORD_GUILD_ID"):
        if config.get(key):
            os.environ[key] = config[key]
    create_bot().run(config["DISCORD_TOKEN"])
