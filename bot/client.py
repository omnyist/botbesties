from __future__ import annotations

import logging

import twitchio
from twitchio import eventsub
from twitchio.ext import commands

from .components.dynamic import DynamicCommands
from .components.management import ManagementCommands

logger = logging.getLogger("bot")


class BotClient(commands.Bot):
    """TwitchIO bot that reads commands from the Django database.

    Each BotClient instance represents one bot identity (e.g., Elsydeon)
    connected to one or more channels.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        bot_id: str,
        bot_name: str,
        token: str,
        refresh_token: str,
        channels: list[dict],
    ) -> None:
        self.bot_name = bot_name
        self._channel_map = {ch["name"]: ch for ch in channels}

        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            bot_id=bot_id,
            prefix="!",
        )

        self._initial_token = token
        self._initial_refresh = refresh_token

    async def setup_hook(self) -> None:
        await self.add_token(self._initial_token, self._initial_refresh)

        for channel_info in self._channel_map.values():
            broadcaster_id = channel_info["twitch_channel_id"]
            payload = eventsub.ChatMessageSubscription(
                broadcaster_user_id=broadcaster_id,
                user_id=self.bot_id,
            )
            try:
                await self.subscribe_websocket(payload=payload)
                logger.info(
                    "[%s] Subscribed to chat in #%s",
                    self.bot_name,
                    channel_info["name"],
                )
            except Exception:
                logger.exception(
                    "[%s] Failed to subscribe to #%s",
                    self.bot_name,
                    channel_info["name"],
                )

        await self.add_component(ManagementCommands(self))
        await self.add_component(DynamicCommands(self))

        logger.info("[%s] Setup complete.", self.bot_name)

    async def event_ready(self) -> None:
        logger.info("[%s] Bot is ready (ID: %s).", self.bot_name, self.bot_id)
