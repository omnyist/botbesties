from __future__ import annotations

import logging

from twitchio.ext import commands

logger = logging.getLogger("bot")


class ErrorHandler(commands.Component):
    """Suppress CommandNotFound and log real errors."""

    def __init__(self, bot: commands.Bot) -> None:
        self.original = bot.event_command_error
        bot.event_command_error = self.event_command_error
        self.bot = bot

    async def component_teardown(self) -> None:
        self.bot.event_command_error = self.original

    async def event_command_error(
        self, payload: commands.CommandErrorPayload
    ) -> None:
        ctx = payload.context
        command = ctx.command
        error = payload.exception

        if command and command.has_error and ctx.error_dispatched:
            return

        if isinstance(error, commands.CommandNotFound):
            return

        msg = f'Error in command "{ctx.command}":\n'
        logger.error(msg, exc_info=error)
