from __future__ import annotations

import logging
import random

import twitchio
from asgiref.sync import sync_to_async
from django.db.models import F
from twitchio.ext import commands

from .skills import SKILL_REGISTRY
from .skills import discover_skills
from .variables import VariableContext
from .variables import create_registry

logger = logging.getLogger("bot")

# Commands handled by ManagementCommands — skip in the router
BUILTIN_COMMANDS = frozenset(
    {
        "addcom",
        "editcom",
        "delcom",
        "commands",
        "id",
        "alias",
        "unalias",
        "aliases",
        "count",
        "counters",
    }
)


class CommandRouter(commands.Component):
    """Unified message handler for aliases, commands, and skills.

    Processes messages in this order:

    1. Self-message guard
    2. Prefix check (!)
    3. Skip built-in management commands
    4. Alias resolution (rewrites trigger to target)
    5. Command lookup — type-based dispatch (text, lottery, random_list, counter)
    6. Skill handler fallback (Python-coded complex behaviors)
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._registry = create_registry()
        discover_skills()

    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        # 1. Self-message guard
        if payload.chatter and str(payload.chatter.id) == str(self.bot.bot_id):
            return

        text = payload.text.strip()
        if not text.startswith("!"):
            return

        parts = text[1:].split(maxsplit=1)
        if not parts:
            return

        cmd_name = parts[0].lower()
        raw_args = parts[1] if len(parts) > 1 else ""

        # 3. Skip built-in commands
        if cmd_name in BUILTIN_COMMANDS:
            return

        broadcaster_id = str(payload.broadcaster.id)

        # 4. Alias resolution
        from core.models import Alias

        try:
            alias = await sync_to_async(Alias.objects.get)(
                channel__twitch_channel_id=broadcaster_id,
                channel__is_active=True,
                name=cmd_name,
            )
            # Rewrite: alias target may include args (e.g., "count death")
            alias_parts = alias.target.split(maxsplit=1)
            cmd_name = alias_parts[0].lower()
            # Prepend alias args before user args
            alias_args = alias_parts[1] if len(alias_parts) > 1 else ""
            if alias_args and raw_args:
                raw_args = f"{alias_args} {raw_args}"
            elif alias_args:
                raw_args = alias_args
        except Alias.DoesNotExist:
            pass

        # 5. Command lookup — type-based dispatch
        from core.models import Command

        try:
            cmd = await sync_to_async(Command.objects.get)(
                channel__twitch_channel_id=broadcaster_id,
                channel__is_active=True,
                name=cmd_name,
                enabled=True,
            )
        except Command.DoesNotExist:
            cmd = None

        if cmd is not None:
            response_text = await self._resolve_response(cmd, payload, broadcaster_id)
            if response_text is None:
                return

            # Common pipeline: increment use_count → variables → /me → respond
            cmd.use_count += 1
            await sync_to_async(cmd.save)(update_fields=["use_count"])

            chatter_name = (
                payload.chatter.display_name
                if payload.chatter
                else "someone"
            )
            channel_name = (
                payload.broadcaster.display_name
                if payload.broadcaster
                else ""
            )
            target_arg = (
                raw_args.split()[0].lstrip("@") if raw_args else chatter_name
            )

            context = VariableContext(
                user=chatter_name,
                target=target_arg,
                channel_name=channel_name,
                broadcaster_id=broadcaster_id,
                command_name=cmd_name,
                use_count=cmd.use_count,
                raw_args=raw_args,
            )

            response = await self._registry.process(response_text, context)

            # Handle /me action messages
            use_me = False
            if response.startswith("/me "):
                use_me = True
                response = response[4:]
                # Strip the common "- " separator from Spoonee's commands
                if response.startswith("- "):
                    response = response[2:]

            await payload.respond(response, me=use_me)
            return

        # 6. Skill handler fallback
        if cmd_name in SKILL_REGISTRY:
            from core.models import Skill

            try:
                skill = await sync_to_async(Skill.objects.get)(
                    channel__twitch_channel_id=broadcaster_id,
                    channel__is_active=True,
                    name=cmd_name,
                    enabled=True,
                )
            except Skill.DoesNotExist:
                return

            handler = SKILL_REGISTRY[cmd_name]
            try:
                await handler.handle(payload, raw_args, skill, self.bot)
            except Exception:
                logger.exception(
                    "Skill handler '%s' failed",
                    cmd_name,
                )
            return

    async def _resolve_response(
        self,
        cmd,
        payload: twitchio.ChatMessage,
        broadcaster_id: str,
    ) -> str | None:
        """Resolve response text based on command type.

        Returns the response template string, or None to skip responding.
        """
        from core.models import Command
        from core.models import Counter

        if cmd.type == Command.Type.TEXT:
            return cmd.response

        if cmd.type == Command.Type.LOTTERY:
            odds = cmd.config.get("odds", 5)
            if random.randint(1, 100) <= odds:
                template = cmd.config.get("success", "$(user) wins!")
            else:
                template = cmd.config.get("failure", "Better luck next time!")
            return template

        if cmd.type == Command.Type.RANDOM_LIST:
            responses = cmd.config.get("responses", [])
            if not responses:
                return cmd.response or None
            prefix = cmd.config.get("prefix", "")
            return f"{prefix}{random.choice(responses)}"

        if cmd.type == Command.Type.COUNTER:
            counter_name = cmd.config.get("counter_name", cmd.name)
            from core.models import Channel

            channel = await sync_to_async(Channel.objects.get)(
                twitch_channel_id=broadcaster_id, is_active=True
            )
            counter, created = await sync_to_async(
                Counter.objects.get_or_create
            )(
                channel=channel,
                name=counter_name,
                defaults={"value": 0},
            )
            # Atomic increment
            await sync_to_async(
                Counter.objects.filter(pk=counter.pk).update
            )(value=F("value") + 1)
            await sync_to_async(counter.refresh_from_db)()
            return cmd.response

        return cmd.response
