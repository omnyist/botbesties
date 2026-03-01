from __future__ import annotations

import logging

import twitchio
from asgiref.sync import sync_to_async
from twitchio.ext import commands

logger = logging.getLogger("bot")


class ManagementCommands(commands.Component):
    """Built-in commands for managing text commands via chat.

    !addcom <name> <response>  — Create a new command (mod/broadcaster only)
    !editcom <name> <response> — Edit an existing command (mod/broadcaster only)
    !delcom <name>             — Delete a command (mod/broadcaster only)
    !commands                  — List all enabled commands
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _is_privileged(self, message: twitchio.ChatMessage) -> bool:
        """Check if the user is a moderator or broadcaster."""
        badges = message.badges or []
        badge_ids = [b.id if hasattr(b, "id") else str(b) for b in badges]
        return any(
            badge_id in ("broadcaster", "moderator") for badge_id in badge_ids
        )

    async def _get_channel(self, broadcaster_id: str):
        """Look up the Channel model for a broadcaster."""
        from core.models import Channel

        try:
            return await sync_to_async(
                Channel.objects.get
            )(twitch_channel_id=broadcaster_id, is_active=True)
        except Channel.DoesNotExist:
            return None

    @commands.command(name="addcom")
    async def addcom(self, ctx: commands.Context, name: str, *, response: str) -> None:
        """Create a new text command."""
        if not self._is_privileged(ctx.message):
            return

        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Command

        name = name.lstrip("!")

        exists = await sync_to_async(
            Command.objects.filter(channel=channel, name=name).exists
        )()
        if exists:
            await ctx.send(f"Command !{name} already exists. Use !editcom to update it.")
            return

        await sync_to_async(Command.objects.create)(
            channel=channel,
            name=name,
            response=response,
            created_by=ctx.chatter.name if ctx.chatter else "",
        )

        await ctx.send(f"Command !{name} has been created.")
        logger.info(
            "[%s] Command !%s created by %s",
            self.bot.bot_name,
            name,
            ctx.chatter.name if ctx.chatter else "unknown",
        )

    @commands.command(name="editcom")
    async def editcom(self, ctx: commands.Context, name: str, *, response: str) -> None:
        """Edit an existing text command."""
        if not self._is_privileged(ctx.message):
            return

        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Command

        name = name.lstrip("!")

        try:
            cmd = await sync_to_async(Command.objects.get)(
                channel=channel, name=name
            )
        except Command.DoesNotExist:
            await ctx.send(f"Command !{name} does not exist.")
            return

        cmd.response = response
        await sync_to_async(cmd.save)()

        await ctx.send(f"Command !{name} has been updated.")
        logger.info(
            "[%s] Command !%s edited by %s",
            self.bot.bot_name,
            name,
            ctx.chatter.name if ctx.chatter else "unknown",
        )

    @commands.command(name="delcom")
    async def delcom(self, ctx: commands.Context, name: str) -> None:
        """Delete a text command."""
        if not self._is_privileged(ctx.message):
            return

        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Command

        name = name.lstrip("!")

        try:
            cmd = await sync_to_async(Command.objects.get)(
                channel=channel, name=name
            )
        except Command.DoesNotExist:
            await ctx.send(f"Command !{name} does not exist.")
            return

        await sync_to_async(cmd.delete)()

        await ctx.send(f"Command !{name} has been deleted.")
        logger.info(
            "[%s] Command !%s deleted by %s",
            self.bot.bot_name,
            name,
            ctx.chatter.name if ctx.chatter else "unknown",
        )

    @commands.command(name="commands")
    async def list_commands(self, ctx: commands.Context) -> None:
        """List all enabled commands for this channel."""
        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Command

        cmd_names = []
        async for cmd in sync_to_async(
            lambda: Command.objects.filter(channel=channel, enabled=True)
            .order_by("name")
            .values_list("name", flat=True)
        )():
            cmd_names.append(cmd)

        if cmd_names:
            names_str = ", ".join(f"!{n}" for n in cmd_names)
            await ctx.send(f"Commands: {names_str}")
        else:
            await ctx.send("No commands have been added yet.")
