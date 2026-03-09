from __future__ import annotations

import asyncio
import logging
import random
import time

from asgiref.sync import sync_to_async

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.twitch import TWITCH_API_BASE
from core.twitch import twitch_request

logger = logging.getLogger("bot")


CHEMICALS = [
    "serotonin",
    "dopamine",
    "oxytocin",
    "endorphins",
    "copium",
    "hopium",
    "adrenaline",
    "melatonin",
    "norepinephrine",
]


def _ordinal(n: int) -> str:
    """Format an integer as an ordinal string (1st, 2nd, 3rd, 14th, etc.)."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]}"


class LizardRouletteHandler(SkillHandler):
    """!lizardroulette — Roll the dice. Lose and get timed out."""

    name = "lizardroulette"

    def __init__(self):
        self._cooldowns: dict[str, float] = {}
        self._bullets: dict[str, int] = {}

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        if not chatter:
            return

        broadcaster_id = str(payload.broadcaster.id)
        chatter_id = str(chatter.id)
        chatter_name = chatter.display_name
        config = skill.config or {}

        # --- Per-user cooldown (scoped to channel) ---
        cooldown = config.get("cooldown", 300)
        now = time.monotonic()
        cooldown_key = f"{broadcaster_id}:{chatter_id}"
        last_used = self._cooldowns.get(cooldown_key)
        if last_used and (now - last_used) < cooldown:
            cooldown_response = config.get("cooldown_response")
            if cooldown_response:
                remaining = int(cooldown - (now - last_used))
                message = cooldown_response.replace(
                    "$(user)", chatter_name
                ).replace("$(remaining)", str(remaining))
                await send_reply(payload, message, bot_id=bot.bot_id)
            return

        self._cooldowns[cooldown_key] = now

        # --- Look up channel for stat tracking ---
        from core.models import Channel

        try:
            channel = await sync_to_async(Channel.objects.get)(
                twitch_channel_id=broadcaster_id,
                is_active=True,
            )
        except Channel.DoesNotExist:
            logger.warning("No active channel found for broadcaster %s", broadcaster_id)
            return

        # --- Check for loaded gun ---
        bullets = self._bullets.get(broadcaster_id, 0)
        if bullets > 0:
            self._bullets[broadcaster_id] = bullets - 1
            is_loss = True
        else:
            odds = config.get("odds", 16)
            is_loss = random.randint(1, 100) <= odds

        # --- Resolve outcome ---
        if is_loss:
            # Loss — track death
            deaths = await self._update_stat(
                channel, chatter_id, chatter.name, "deaths"
            )
            if deaths == 1:
                failure = config.get(
                    "failure_first",
                    "You lose $(user). Reach for the sky. 3, 2, 1... LizardWithAGun",
                )
            else:
                failure = config.get(
                    "failure",
                    "Damnit, for the $(deaths) time, you lose $(user). Reach for the sky. 3, 2, 1... LizardWithAGun",
                )
            message = failure.replace("$(user)", chatter_name).replace(
                "$(deaths)", _ordinal(deaths)
            )
            await send_reply(payload, message, bot_id=bot.bot_id)

            timeout_delay = config.get("timeout_delay", 5)
            timeout_duration = config.get("timeout_duration", 600)
            await asyncio.sleep(timeout_delay)
            timed_out = await self._timeout_user(
                channel, broadcaster_id, chatter_id, timeout_duration
            )

            if not timed_out:
                timeout_failed = config.get("timeout_failed")
                if timeout_failed:
                    msg = timeout_failed.replace("$(user)", chatter_name)
                    await send_reply(payload, msg, bot_id=bot.bot_id)
        else:
            # Win
            success = config.get(
                "success",
                "*click* You survived $(user). Congrats, have some $(chemical). bardLizard",
            )
            chemical = random.choice(CHEMICALS)
            message = success.replace("$(user)", chatter_name).replace(
                "$(chemical)", chemical
            )
            await send_reply(payload, message, bot_id=bot.bot_id)

    async def _update_stat(self, channel, twitch_id, username, stat_key):
        """Increment a stat and return the new value."""
        from core.models import SkillStat

        stat, created = await sync_to_async(SkillStat.objects.get_or_create)(
            channel=channel,
            skill_name="lizardroulette",
            twitch_id=twitch_id,
            defaults={"twitch_username": username, "stats": {stat_key: 1}},
        )
        if not created:
            stat.twitch_username = username
            stat.stats[stat_key] = stat.stats.get(stat_key, 0) + 1
            await sync_to_async(stat.save)(update_fields=["twitch_username", "stats"])
        return stat.stats.get(stat_key, 1)

    async def _timeout_user(
        self,
        channel,
        broadcaster_id: str,
        user_id: str,
        duration: int,
    ) -> bool:
        """Issue a timeout via the Twitch Helix moderation API.

        Returns True if the timeout succeeded, False otherwise.
        """
        url = (
            f"{TWITCH_API_BASE}/moderation/bans"
            f"?broadcaster_id={broadcaster_id}"
            f"&moderator_id={broadcaster_id}"
        )
        body = {
            "data": {
                "user_id": user_id,
                "duration": duration,
                "reason": "lizardroulette",
            }
        }

        response = await twitch_request(channel, "POST", url, json=body)
        if response is None:
            logger.warning(
                "Failed to timeout user %s in #%s (no response)",
                user_id,
                channel.twitch_channel_name,
            )
            return False

        if response.status_code >= 400:
            logger.warning(
                "Timeout API returned %s for user %s in #%s",
                response.status_code,
                user_id,
                channel.twitch_channel_name,
            )
            return False

        return True


register_skill(LizardRouletteHandler())
