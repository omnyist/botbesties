from __future__ import annotations

import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger("bot")


class Command(BaseCommand):
    help = "Run TwitchIO bot instances for all active bots."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Botbesties..."))

        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nShutting down..."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            logger.error("Bot error: %s", e, exc_info=True)
            raise

    async def _run(self):
        from core.models import Bot as BotModel

        from bot.client import BotClient

        bots_qs = BotModel.objects.filter(
            channels__is_active=True,
        ).distinct()

        bot_instances = []

        for bot_record in bots_qs:
            if not bot_record.access_token:
                logger.warning(
                    "Skipping %s — no access token. Run the setup flow first.",
                    bot_record.name,
                )
                continue

            channels = []
            for ch in bot_record.channels.filter(is_active=True):
                channels.append(
                    {
                        "name": ch.twitch_channel_name,
                        "twitch_channel_id": ch.twitch_channel_id,
                    }
                )

            if not channels:
                logger.warning("Skipping %s — no active channels.", bot_record.name)
                continue

            client = BotClient(
                client_id=settings.TWITCH_CLIENT_ID,
                client_secret=settings.TWITCH_CLIENT_SECRET,
                bot_id=bot_record.twitch_user_id,
                bot_name=bot_record.name,
                token=bot_record.access_token,
                refresh_token=bot_record.refresh_token,
                channels=channels,
            )
            bot_instances.append(client)
            logger.info(
                "Loaded %s (channels: %s)",
                bot_record.name,
                ", ".join(f"#{ch['name']}" for ch in channels),
            )

        if not bot_instances:
            logger.error(
                "No bots to run. Create a Bot in the admin and complete the setup flow."
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Starting {len(bot_instances)} bot(s)...")
        )

        tasks = [asyncio.create_task(bot.start()) for bot in bot_instances]

        try:
            await asyncio.gather(*tasks)
        except Exception:
            logger.exception("Bot task failed.")
            for task in tasks:
                task.cancel()
            raise
