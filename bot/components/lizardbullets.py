"""Lizard bullet loader — silently loads the lizard's revolver on a timer."""

from __future__ import annotations

import asyncio
import logging
import random

from asgiref.sync import sync_to_async
from twitchio.ext import commands

from bot.skills import SKILL_REGISTRY
from core.twitch import TWITCH_API_BASE
from core.twitch import twitch_request

logger = logging.getLogger("bot")

TICK_INTERVAL = 30  # seconds
BULLET_ODDS = 651  # 1-in-651 per tick
CHAMBER_COUNT = 6


class LizardBullets(commands.Component):
    """Silently loads the lizard's revolver on a background timer.

    Every 30 seconds, rolls a 1/651 chance per channel to load all 6
    chambers. When loaded, the next 6 uses of !lizardroulette are
    guaranteed losses. No announcement — happens in complete silence.
    Only ticks while the channel is live.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None
        self._channel_cache: dict[str, object] = {}

    async def component_load(self) -> None:
        self._task = asyncio.create_task(self._tick_loop())

    async def component_teardown(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _tick_loop(self) -> None:
        """Roll for bullet loading forever, sleeping between ticks."""
        try:
            await asyncio.sleep(10)  # wait for bot to fully connect
            while True:
                for channel_info in self.bot._channel_map.values():
                    try:
                        await self._tick_channel(channel_info)
                    except Exception:
                        logger.exception(
                            "[LizardBullets] Error processing #%s",
                            channel_info["name"],
                        )
                await asyncio.sleep(TICK_INTERVAL)
        except asyncio.CancelledError:
            logger.info("[LizardBullets] Tick loop cancelled.")

    async def _get_channel(self, channel_info: dict) -> object:
        """Load and cache the Django Channel model for twitch_request."""
        name = channel_info["name"]
        if name not in self._channel_cache:
            from core.models import Channel

            channel = await sync_to_async(
                Channel.objects.select_related("bot").get
            )(twitch_channel_name=name, is_active=True)
            self._channel_cache[name] = channel
        return self._channel_cache[name]

    async def _is_live(self, channel, broadcaster_id: str) -> bool:
        """Check if the broadcaster is currently live."""
        response = await twitch_request(
            channel,
            "GET",
            f"{TWITCH_API_BASE}/streams",
            params={"user_id": broadcaster_id},
        )
        if response is None or response.status_code != 200:
            return False
        data = response.json().get("data", [])
        return len(data) > 0

    async def _tick_channel(self, channel_info: dict) -> None:
        """Roll once for a single channel, only if live."""
        broadcaster_id = channel_info["twitch_channel_id"]
        channel = await self._get_channel(channel_info)

        if not await self._is_live(channel, broadcaster_id):
            return

        if random.randint(1, BULLET_ODDS) != 1:
            return

        handler = SKILL_REGISTRY.get("lizardroulette")
        if handler is None:
            return

        handler._bullets[broadcaster_id] = CHAMBER_COUNT
        logger.info(
            "[LizardBullets] Gun loaded in #%s",
            channel_info["name"],
        )
