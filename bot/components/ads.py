"""Ad announce — subscribes to Synthfunc Redis events and announces in chat."""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings
from twitchio.ext import commands

logger = logging.getLogger("bot")

DEFAULT_MESSAGES = {
    "warning": (
        "This is a message from the emergency ad break system. "
        "Incoming ad in $(seconds) seconds!"
    ),
    "running": (
        "Running $(duration) seconds of ads now. "
        "We apologize for the interruption to your programming."
    ),
    "ended": (
        "The ad block has completed. "
        "You may now return to your irregularly scheduled programming."
    ),
    "enabled": "Ad rotation enabled.",
    "disabled": "Ad rotation disabled.",
}

DEFAULT_WARNING_INTERVALS = [60, 5]
WARNING_TOLERANCE = 5


class AdAnnounce(commands.Component):
    """Subscribes to Synthfunc ad events via Redis and announces in chat."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None
        self._slug_map: dict[str, str] = {}

    async def component_load(self) -> None:
        self._slug_map = {
            info["name"]: info["twitch_channel_id"]
            for info in self.bot._channel_map.values()
        }
        self._task = asyncio.create_task(self._listen_loop())

    async def component_teardown(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _listen_loop(self) -> None:
        """Subscribe to Redis ad event channels and process messages."""
        try:
            await asyncio.sleep(10)
            redis_channels = [
                f"events:{slug}:ads" for slug in self._slug_map
            ]
            if not redis_channels:
                logger.info("[AdAnnounce] No channels to subscribe to.")
                return

            while True:
                client = None
                pubsub = None
                try:
                    client = aioredis.from_url(settings.REDIS_URL)
                    pubsub = client.pubsub()
                    await pubsub.subscribe(*redis_channels)
                    logger.info(
                        "[AdAnnounce] Subscribed to %d channel(s).",
                        len(redis_channels),
                    )

                    async for raw in pubsub.listen():
                        if raw["type"] != "message":
                            continue
                        try:
                            await self._handle_event(
                                raw["channel"], raw["data"]
                            )
                        except Exception:
                            logger.exception("[AdAnnounce] Error handling event")

                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "[AdAnnounce] Redis error, reconnecting in 5s..."
                    )
                    await asyncio.sleep(5)
                finally:
                    if pubsub:
                        try:
                            await pubsub.close()
                        except Exception:
                            pass
                    if client:
                        try:
                            await client.close()
                        except Exception:
                            pass

        except asyncio.CancelledError:
            logger.info("[AdAnnounce] Listen loop cancelled.")

    async def _handle_event(self, redis_channel: bytes, raw_data: bytes) -> None:
        """Process a single Redis ad event."""
        slug = redis_channel.decode().split(":")[1]
        broadcaster_id = self._slug_map.get(slug)
        if not broadcaster_id:
            return

        skill = await self._get_skill(slug)
        if not skill:
            return

        event = json.loads(raw_data)
        event_type = event.get("event_type", "")
        data = event.get("data", {})
        config = skill.config or {}
        messages = config.get("messages", DEFAULT_MESSAGES)

        if event_type == "ads:warning":
            await self._handle_warning(broadcaster_id, data, messages, config)
        elif event_type == "ads:running":
            msg = messages.get("running", DEFAULT_MESSAGES["running"])
            msg = msg.replace("$(duration)", str(data.get("duration", 90)))
            await self._send_chat(broadcaster_id, msg)
        elif event_type == "ads:ended":
            msg = messages.get("ended", DEFAULT_MESSAGES["ended"])
            await self._send_chat(broadcaster_id, msg)
        elif event_type == "ads:enabled":
            msg = messages.get("enabled", DEFAULT_MESSAGES["enabled"])
            await self._send_chat(broadcaster_id, msg)
        elif event_type == "ads:disabled":
            msg = messages.get("disabled", DEFAULT_MESSAGES["disabled"])
            await self._send_chat(broadcaster_id, msg)

    async def _handle_warning(
        self,
        broadcaster_id: str,
        data: dict,
        messages: dict,
        config: dict,
    ) -> None:
        """Announce warnings only at configured second thresholds."""
        seconds = data.get("seconds", 0)
        intervals = config.get(
            "warning_intervals", DEFAULT_WARNING_INTERVALS
        )

        for interval in intervals:
            if abs(seconds - interval) <= WARNING_TOLERANCE:
                msg = messages.get("warning", DEFAULT_MESSAGES["warning"])
                msg = msg.replace("$(seconds)", str(seconds))
                await self._send_chat(broadcaster_id, msg)
                return

    async def _send_chat(self, broadcaster_id: str, message: str) -> None:
        """Send a chat message to a channel."""
        try:
            broadcaster = self.bot.create_partialuser(id=broadcaster_id)
            await broadcaster.send_message(
                sender=self.bot.bot_id, message=message
            )
        except Exception:
            logger.exception(
                "[AdAnnounce] Failed to send message to %s", broadcaster_id
            )

    async def _get_skill(self, slug: str):
        """Look up the ads skill for a channel."""
        from core.models import Skill

        return await sync_to_async(
            Skill.objects.filter(
                channel__twitch_channel_name=slug,
                name="ads",
                enabled=True,
            ).first
        )()
