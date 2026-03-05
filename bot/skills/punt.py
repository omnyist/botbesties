"""!punt — 1-second self-timeout for disrespecting lalafells.

Mods and broadcasters are immune.
"""

from __future__ import annotations

import logging

from asgiref.sync import sync_to_async

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.twitch import TWITCH_API_BASE
from core.twitch import twitch_request

logger = logging.getLogger("bot")


class PuntHandler(SkillHandler):
    """!punt — 1-second timeout on the caller."""

    name = "punt"

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        if not chatter:
            return

        chatter_name = chatter.display_name
        config = skill.config or {}

        # Mods and broadcasters are immune
        if chatter.moderator or chatter.broadcaster:
            immune_msg = config.get(
                "immune",
                "/me can't punt $(user)! They're too kawaii~ avalonEYES",
            )
            immune_msg = immune_msg.replace("$(user)", chatter_name)
            await send_reply(payload, immune_msg, bot_id=bot.bot_id)
            return

        # Timeout the caller for 1 second
        timed_out = await self._timeout_user(payload, str(chatter.id), bot)

        if timed_out:
            success_msg = config.get(
                "success",
                "/me punted $(user) for their disrespect, lalafell hater. avalonRAGE",
            )
        else:
            success_msg = config.get(
                "failure",
                "/me tried to punt $(user) but something went wrong!",
            )

        success_msg = success_msg.replace("$(user)", chatter_name)
        await send_reply(payload, success_msg, bot_id=bot.bot_id)

    async def _timeout_user(self, payload, user_id: str, bot) -> bool:
        """Issue a 1-second timeout via the Twitch Helix moderation API."""
        broadcaster_id = str(payload.broadcaster.id)

        from core.models import Channel

        try:
            channel = await sync_to_async(Channel.objects.get)(
                twitch_channel_id=broadcaster_id,
                is_active=True,
            )
        except Channel.DoesNotExist:
            return False

        url = (
            f"{TWITCH_API_BASE}/moderation/bans"
            f"?broadcaster_id={broadcaster_id}"
            f"&moderator_id={broadcaster_id}"
        )
        body = {
            "data": {
                "user_id": user_id,
                "duration": 1,
                "reason": "punt",
            }
        }

        response = await twitch_request(channel, "POST", url, json=body)
        if response is None or response.status_code >= 400:
            return False

        return True


register_skill(PuntHandler())
