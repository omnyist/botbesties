from __future__ import annotations

import logging

from asgiref.sync import sync_to_async
from django.db.models import F
from twitchio.ext import commands

logger = logging.getLogger("bot")


class ManagementCommands(commands.Component):
    """Built-in commands for managing text commands, aliases, and counters.

    !addcom <name> <response>  — Create a new command (mod/broadcaster only)
    !editcom <name> <response> — Edit an existing command (mod/broadcaster only)
    !delcom <name>             — Delete a command (mod/broadcaster only)
    !commands                  — List all enabled commands
    !alias <name> <target>     — Create a command alias (mod/broadcaster only)
    !unalias <name>            — Remove a command alias (mod/broadcaster only)
    !aliases                   — List all aliases
    !count <name> [+|-|set N]  — View or modify a counter (mutations mod/broadcaster)
    !counters                  — List all counters and their values
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _is_privileged(self, ctx: commands.Context) -> bool:
        """Check if the user is a moderator or broadcaster."""
        chatter = ctx.chatter
        return chatter.broadcaster or chatter.moderator

    async def _get_channel(self, broadcaster_id: str):
        """Look up the Channel model for a broadcaster."""
        from core.models import Channel

        try:
            return await sync_to_async(
                Channel.objects.get
            )(twitch_channel_id=broadcaster_id, is_active=True)
        except Channel.DoesNotExist:
            return None

    @commands.command(name="id")
    async def bot_id(self, ctx: commands.Context) -> None:
        """Return the bot's Twitch user ID."""
        await ctx.send(f"My bot ID is {self.bot.bot_id}.")

    @commands.command(name="addcom")
    async def addcom(self, ctx: commands.Context, name: str, *, response: str) -> None:
        """Create a new text command."""
        if not self._is_privileged(ctx):
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
        if not self._is_privileged(ctx):
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
        if not self._is_privileged(ctx):
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

        cmd_names = await sync_to_async(
            lambda: list(
                Command.objects.filter(channel=channel, enabled=True)
                .order_by("name")
                .values_list("name", flat=True)
            )
        )()

        if cmd_names:
            names_str = ", ".join(f"!{n}" for n in cmd_names)
            await ctx.send(f"Commands: {names_str}")
        else:
            await ctx.send("No commands have been added yet.")

    # --- Alias management ---

    @commands.command(name="alias")
    async def add_alias(self, ctx: commands.Context, name: str, *, target: str) -> None:
        """Create a command alias."""
        if not self._is_privileged(ctx):
            return

        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Alias

        name = name.lstrip("!")

        exists = await sync_to_async(
            Alias.objects.filter(channel=channel, name=name).exists
        )()
        if exists:
            await ctx.send(f"Alias !{name} already exists. Use !unalias first.")
            return

        await sync_to_async(Alias.objects.create)(
            channel=channel,
            name=name,
            target=target,
        )

        await ctx.send(f"Alias !{name} → !{target} created.")
        logger.info(
            "[%s] Alias !%s → !%s created by %s",
            self.bot.bot_name,
            name,
            target,
            ctx.chatter.name if ctx.chatter else "unknown",
        )

    @commands.command(name="unalias")
    async def remove_alias(self, ctx: commands.Context, name: str) -> None:
        """Remove a command alias."""
        if not self._is_privileged(ctx):
            return

        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Alias

        name = name.lstrip("!")

        try:
            alias = await sync_to_async(Alias.objects.get)(
                channel=channel, name=name
            )
        except Alias.DoesNotExist:
            await ctx.send(f"Alias !{name} does not exist.")
            return

        await sync_to_async(alias.delete)()

        await ctx.send(f"Alias !{name} has been removed.")
        logger.info(
            "[%s] Alias !%s removed by %s",
            self.bot.bot_name,
            name,
            ctx.chatter.name if ctx.chatter else "unknown",
        )

    @commands.command(name="aliases")
    async def list_aliases(self, ctx: commands.Context) -> None:
        """List all aliases for this channel."""
        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Alias

        alias_list = await sync_to_async(
            lambda: list(
                Alias.objects.filter(channel=channel)
                .order_by("name")
                .values_list("name", "target")
            )
        )()

        if alias_list:
            entries = ", ".join(f"!{name} → !{target}" for name, target in alias_list)
            await ctx.send(f"Aliases: {entries}")
        else:
            await ctx.send("No aliases have been created yet.")

    # --- Counter management ---

    @commands.command(name="count")
    async def count(self, ctx: commands.Context, *, args: str = "") -> None:
        """View or modify a named counter.

        !count <name>          — Show counter value (everyone)
        !count <name> +        — Increment (mod/broadcaster)
        !count <name> -        — Decrement (mod/broadcaster)
        !count <name> set <N>  — Set to value (mod/broadcaster)
        """
        parts = args.split() if args else []
        if not parts:
            await ctx.send("Usage: !count <name> [+|-|set <N>]")
            return

        counter_name = parts[0].lower()
        action = parts[1] if len(parts) > 1 else None
        broadcaster_id = str(ctx.broadcaster.id)

        from core.models import Counter

        if action in ("+", "-", "set"):
            if not self._is_privileged(ctx):
                return

            if action == "set":
                if len(parts) < 3:
                    await ctx.send("Usage: !count <name> set <N>")
                    return
                try:
                    new_value = int(parts[2])
                except ValueError:
                    await ctx.send("Value must be a number.")
                    return

                channel = await self._get_channel(broadcaster_id)
                if not channel:
                    return

                counter, created = await sync_to_async(
                    Counter.objects.update_or_create
                )(
                    channel=channel,
                    name=counter_name,
                    defaults={"value": new_value},
                )

                label = counter.label or counter.name.title()
                await ctx.send(f"{label}: {new_value}")
                return

            # Increment or decrement
            delta = 1 if action == "+" else -1

            channel = await self._get_channel(broadcaster_id)
            if not channel:
                return

            counter, created = await sync_to_async(
                Counter.objects.get_or_create
            )(
                channel=channel,
                name=counter_name,
                defaults={"value": 0},
            )

            # Atomic update
            await sync_to_async(
                Counter.objects.filter(pk=counter.pk).update
            )(value=F("value") + delta)

            # Refresh to get the updated value
            await sync_to_async(counter.refresh_from_db)()
            label = counter.label or counter.name.title()
            await ctx.send(f"{label}: {counter.value}")
            return

        # No action — show the counter value
        try:
            counter = await sync_to_async(Counter.objects.get)(
                channel__twitch_channel_id=broadcaster_id,
                channel__is_active=True,
                name=counter_name,
            )
        except Counter.DoesNotExist:
            await ctx.send(f"Counter '{counter_name}' does not exist.")
            return

        label = counter.label or counter.name.title()
        await ctx.send(f"{label}: {counter.value}")

    @commands.command(name="counters")
    async def list_counters(self, ctx: commands.Context) -> None:
        """List all counters and their values for this channel."""
        channel = await self._get_channel(str(ctx.broadcaster.id))
        if not channel:
            return

        from core.models import Counter

        counter_list = await sync_to_async(
            lambda: list(
                Counter.objects.filter(channel=channel)
                .order_by("name")
                .values_list("name", "label", "value")
            )
        )()

        if counter_list:
            entries = ", ".join(
                f"{label or name.title()}: {value}"
                for name, label, value in counter_list
            )
            await ctx.send(f"Counters: {entries}")
        else:
            await ctx.send("No counters have been created yet.")
