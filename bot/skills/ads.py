"""!ads — Ad rotation control.

Usage:
    !ads           — Show ad scheduler status
    !ads on        — Enable ad rotation (mod/broadcaster only)
    !ads off       — Disable ad rotation (mod/broadcaster only)
"""

from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.synthfunc import disable_ads
from core.synthfunc import enable_ads
from core.synthfunc import get_ads_status

logger = logging.getLogger("bot")

DEFAULT_MESSAGES = {
    "status_on": "Ads: ON | Next ad in $(remaining) | $(interval)m interval, $(duration)s duration",
    "status_off": "Ads: OFF",
    "enable_failed": "Failed to enable ads.",
    "disable_failed": "Failed to disable ads.",
}


class AdsHandler(SkillHandler):
    """!ads — Ad rotation control."""

    name = "ads"

    async def handle(self, payload, args, skill, bot):
        sub = args.strip().lower() if args else ""
        tenant_slug = skill.channel.twitch_channel_name
        config = skill.config or {}
        messages = config.get("messages", DEFAULT_MESSAGES)

        if sub == "on":
            chatter = payload.chatter
            if not chatter or not (chatter.moderator or chatter.broadcaster):
                return

            result = await enable_ads(tenant_slug)
            if not result:
                msg = messages.get("enable_failed", DEFAULT_MESSAGES["enable_failed"])
                await send_reply(payload, msg, bot_id=bot.bot_id)

        elif sub == "off":
            chatter = payload.chatter
            if not chatter or not (chatter.moderator or chatter.broadcaster):
                return

            result = await disable_ads(tenant_slug)
            if not result:
                msg = messages.get("disable_failed", DEFAULT_MESSAGES["disable_failed"])
                await send_reply(payload, msg, bot_id=bot.bot_id)

        else:
            status = await get_ads_status(tenant_slug)
            if not status:
                await send_reply(
                    payload, "Could not fetch ad status.", bot_id=bot.bot_id
                )
                return

            if status.get("enabled"):
                msg = messages.get("status_on", DEFAULT_MESSAGES["status_on"])
                ad_config = status.get("config", {})
                interval = ad_config.get("interval", 30)
                duration = ad_config.get("duration", 90)
                remaining = self._format_remaining(status.get("next_time"))
                msg = (
                    msg.replace("$(remaining)", remaining)
                    .replace("$(interval)", str(interval))
                    .replace("$(duration)", str(duration))
                )
            else:
                msg = messages.get("status_off", DEFAULT_MESSAGES["status_off"])

            await send_reply(payload, msg, bot_id=bot.bot_id)

    @staticmethod
    def _format_remaining(next_time_str: str | None) -> str:
        """Format time remaining until next ad as human-readable string."""
        if not next_time_str:
            return "unknown"

        try:
            next_time = datetime.fromisoformat(next_time_str)
            now = datetime.now(UTC)
            delta = next_time - now
            total_seconds = max(0, int(delta.total_seconds()))

            minutes = total_seconds // 60
            seconds = total_seconds % 60

            if minutes > 0:
                return f"{minutes}m {seconds}s"
            return f"{seconds}s"
        except (ValueError, TypeError):
            return "unknown"


register_skill(AdsHandler())
