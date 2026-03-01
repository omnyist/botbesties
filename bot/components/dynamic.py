from __future__ import annotations

import logging
import re

import twitchio
from asgiref.sync import sync_to_async
from twitchio.ext import commands

logger = logging.getLogger("bot")

VARIABLE_PATTERN = re.compile(r"\$\((\w+)(?:\s+([^)]+))?\)")


def process_variables(
    response: str,
    *,
    user: str,
    channel: str,
    count: int,
) -> str:
    """Replace response variables with their values.

    Supported variables:
        $(user)          — Username who triggered the command
        $(channel)       — Current channel name
        $(count)         — Command use count
        $(random N-M)    — Random number in range
        $(pick a,b,c)    — Random choice from list
    """
    import random

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1).lower()
        var_args = match.group(2)

        if var_name == "user":
            return user
        elif var_name == "channel":
            return channel
        elif var_name == "count":
            return str(count)
        elif var_name == "random" and var_args:
            try:
                parts = var_args.split("-")
                low, high = int(parts[0]), int(parts[1])
                return str(random.randint(low, high))
            except (ValueError, IndexError):
                return match.group(0)
        elif var_name == "pick" and var_args:
            choices = [c.strip() for c in var_args.split(",")]
            return random.choice(choices) if choices else match.group(0)

        return match.group(0)

    return VARIABLE_PATTERN.sub(replace_var, response)


class DynamicCommands(commands.Component):
    """Handles DB-defined text commands.

    Listens to all chat messages, checks if they start with the bot prefix,
    looks up the command in the database, processes response variables,
    and sends the response.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        text = payload.text.strip()
        if not text.startswith("!"):
            return

        parts = text[1:].split(maxsplit=1)
        if not parts:
            return

        cmd_name = parts[0].lower()

        # Skip built-in management commands
        if cmd_name in ("addcom", "editcom", "delcom", "commands"):
            return

        broadcaster_id = str(payload.broadcaster.id)

        from core.models import Command

        try:
            cmd = await sync_to_async(Command.objects.get)(
                channel__twitch_channel_id=broadcaster_id,
                channel__is_active=True,
                name=cmd_name,
                enabled=True,
            )
        except Command.DoesNotExist:
            return

        # Increment use count
        cmd.use_count += 1
        await sync_to_async(cmd.save)(update_fields=["use_count"])

        chatter_name = payload.chatter.name if payload.chatter else "someone"
        channel_name = payload.broadcaster.name if payload.broadcaster else ""

        response = process_variables(
            cmd.response,
            user=chatter_name,
            channel=channel_name,
            count=cmd.use_count,
        )

        await payload.respond(response)
