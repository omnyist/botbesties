from __future__ import annotations

import logging
from datetime import UTC
from datetime import datetime

from asgiref.sync import sync_to_async

from bot.skills import SkillHandler
from bot.skills import register_skill
from core.twitch import TWITCH_API_BASE
from core.twitch import twitch_request

logger = logging.getLogger("bot")


class FollowCheckHandler(SkillHandler):
    """!checkme — Check if the chatter follows the channel and for how long."""

    name = "checkme"

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        if not chatter:
            return

        broadcaster_id = str(payload.broadcaster.id)
        chatter_id = str(chatter.id)
        chatter_name = chatter.display_name

        from core.models import Channel

        try:
            channel = await sync_to_async(Channel.objects.get)(
                twitch_channel_id=broadcaster_id,
                is_active=True,
            )
        except Channel.DoesNotExist:
            logger.warning(
                "No active channel found for broadcaster %s", broadcaster_id
            )
            return

        # Broadcaster can't follow themselves.
        if chatter_id == broadcaster_id:
            await payload.respond(
                f"@{chatter_name}, you are the broadcaster!"
            )
            return

        if not channel.owner_access_token:
            await payload.respond(
                f"@{chatter_name}, follow check is not available right now."
            )
            return

        follow_data = await self._fetch_follow(
            channel,
            broadcaster_id,
            chatter_id,
        )

        if follow_data is False:
            await payload.respond(
                f"@{chatter_name}, follow check is not available right now."
            )
            return

        if follow_data is None:
            await payload.respond(
                f"@{chatter_name}, you are not following this channel."
            )
            return

        followed_at_str = follow_data["followed_at"]
        followed_at = datetime.fromisoformat(
            followed_at_str.replace("Z", "+00:00")
        )
        timesince = format_timesince(followed_at)

        await payload.respond(
            f"@{chatter_name}, you have been following for {timesince}!"
        )

    async def _fetch_follow(
        self,
        channel,
        broadcaster_id: str,
        user_id: str,
    ) -> dict | None | bool:
        """Fetch follow relationship from Twitch API.

        Returns:
            dict — user follows (follow data)
            None — user does not follow (confirmed by API)
            False — could not check (API/token error)
        """
        url = f"{TWITCH_API_BASE}/channels/followers"
        params = {
            "broadcaster_id": broadcaster_id,
            "user_id": user_id,
        }

        response = await twitch_request(
            channel, "GET", url, params=params
        )
        if response is None:
            return False

        if response.status_code >= 400:
            logger.warning(
                "Followers API returned %s for user %s in channel %s",
                response.status_code,
                user_id,
                broadcaster_id,
            )
            return False

        data = response.json()
        if data.get("data"):
            return data["data"][0]
        return None


def format_timesince(followed_at: datetime) -> str:
    """Format the time since a follow as a human-readable string."""
    now = datetime.now(UTC)
    delta = now - followed_at
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds} second{'s' if total_seconds != 1 else ''}"

    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"{total_minutes} minute{'s' if total_minutes != 1 else ''}"

    total_hours = total_minutes // 60
    if total_hours < 24:
        return f"{total_hours} hour{'s' if total_hours != 1 else ''}"

    total_days = delta.days

    if total_days < 30:
        return f"{total_days} day{'s' if total_days != 1 else ''}"

    months = total_days // 30
    years = months // 12
    remaining_months = months % 12

    if years > 0 and remaining_months > 0:
        return (
            f"{years} year{'s' if years != 1 else ''}, "
            f"{remaining_months} month{'s' if remaining_months != 1 else ''}"
        )
    elif years > 0:
        return f"{years} year{'s' if years != 1 else ''}"

    return f"{months} month{'s' if months != 1 else ''}"


register_skill(FollowCheckHandler())
