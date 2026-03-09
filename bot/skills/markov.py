"""!markov — Generate fake chat messages from a 2nd-order Markov chain."""

from __future__ import annotations

import json
import logging
import random

import redis.asyncio as aioredis
from django.conf import settings

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.synthfunc import get_chat_messages

logger = logging.getLogger("bot")

CACHE_TTL = 21600  # 6 hours
CANDIDATES = 10
MIN_WORDS = 5
START = "\x02"
END = "\x03"
SEP = "\x00"


def build_chain(messages: list[str]) -> dict[str, list[str]]:
    """Build a 1st-order Markov chain from a list of messages."""
    chain: dict[str, list[str]] = {}
    for msg in messages:
        words = msg.split()
        if len(words) < 3:
            continue
        chain.setdefault(START, []).append(words[0])
        for i in range(len(words) - 1):
            chain.setdefault(words[i], []).append(words[i + 1])
        chain.setdefault(words[-1], []).append(END)
    return chain


def generate_sentence(
    chain: dict[str, list[str]], max_words: int = 30
) -> str | None:
    """Walk the chain to produce a sentence."""
    if START not in chain:
        return None

    word = random.choice(chain[START])
    words = [word]

    for _ in range(max_words - 1):
        if word not in chain:
            break
        next_word = random.choice(chain[word])
        if next_word == END:
            break
        words.append(next_word)
        word = next_word

    return " ".join(words)


class MarkovHandler(SkillHandler):
    """!markov — Generate a sentence from chat history."""

    name = "markov"

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        if not chatter:
            return

        tenant_slug = skill.channel.twitch_channel_name

        if args.strip().lower() == "rebuild":
            if not (chatter.moderator or chatter.broadcaster):
                return
            count = await self._rebuild(tenant_slug)
            if count:
                await send_reply(
                    payload,
                    f"Markov chain rebuilt from {count:,} messages.",
                    bot_id=bot.bot_id,
                )
            else:
                await send_reply(
                    payload,
                    "Could not rebuild — no messages available.",
                    bot_id=bot.bot_id,
                )
            return

        sentence = await self._generate(tenant_slug)
        if sentence is None:
            await self._rebuild(tenant_slug)
            sentence = await self._generate(tenant_slug)

        if sentence:
            await send_reply(payload, sentence, bot_id=bot.bot_id)
        else:
            await send_reply(
                payload,
                "Not enough chat data yet.",
                bot_id=bot.bot_id,
            )

    async def _rebuild(self, tenant_slug: str) -> int | None:
        """Fetch messages from Synthfunc, build chain, cache in Redis.

        Returns the number of messages used, or None on failure.
        """
        messages = await get_chat_messages(tenant_slug)
        if not messages:
            return None

        chain = build_chain(messages)
        if not chain:
            return None

        client = aioredis.from_url(settings.REDIS_URL)
        try:
            await client.set(
                f"markov:{tenant_slug}",
                json.dumps(chain),
                ex=CACHE_TTL,
            )
        finally:
            await client.close()

        logger.info(
            "[Markov] Chain built for %s from %d messages (%d transitions).",
            tenant_slug,
            len(messages),
            len(chain),
        )
        return len(messages)

    async def _generate(self, tenant_slug: str) -> str | None:
        """Read the cached chain from Redis and generate a sentence."""
        client = aioredis.from_url(settings.REDIS_URL)
        try:
            raw = await client.get(f"markov:{tenant_slug}")
        finally:
            await client.close()

        if raw is None:
            return None

        chain = json.loads(raw)
        candidates = [generate_sentence(chain) for _ in range(CANDIDATES)]
        candidates = [s for s in candidates if s is not None]
        if not candidates:
            return None
        long = [s for s in candidates if len(s.split()) >= MIN_WORDS]
        return random.choice(long) if long else max(candidates, key=len)


register_skill(MarkovHandler())
