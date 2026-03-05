"""!cute — Compliment someone. Or try complimenting the bot.

Usage:
    !cute          — You're cute
    !cute @kefka   — kefka is cute
    !cute elsydeon — avalonREVERSE
"""

from __future__ import annotations

import logging

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill

logger = logging.getLogger("bot")


class CuteHandler(SkillHandler):
    """!cute — Compliment someone, pass it on."""

    name = "cute"

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        if not chatter:
            return

        config = skill.config or {}
        bot_name = config.get("bot_name", "elsydeon")
        bot_response = config.get("bot_response", "avalonREVERSE")
        template = config.get("response", "$(target) is cute, pass it on.")

        if args:
            target = args.strip().lstrip("@")
        else:
            target = chatter.display_name

        if target.lower() == bot_name.lower():
            await send_reply(payload, bot_response, bot_id=bot.bot_id)
            return

        message = template.replace("$(target)", target)
        await send_reply(payload, message, bot_id=bot.bot_id)


register_skill(CuteHandler())
