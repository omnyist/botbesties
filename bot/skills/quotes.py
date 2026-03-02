"""!quote — Quote commands powered by Synthfunc.

Usage:
    !quote              — Random quote
    !quote 42           — Quote by number
    !quote search fish  — Search quotes by text
    !quote user bryan   — Quotes by a specific person
    !quote add @user Something funny they said
    !quote latest       — Most recent quote
    !quote stats bryan  — Quote stats for a user
"""

from __future__ import annotations

import logging

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.synthfunc import create_quote
from core.synthfunc import get_latest_quote
from core.synthfunc import get_quote_by_number
from core.synthfunc import get_quote_stats
from core.synthfunc import get_quotes_by_user
from core.synthfunc import get_random_quote
from core.synthfunc import search_quotes

logger = logging.getLogger("bot")


def _format_quote(quote: dict) -> str:
    """Format a quote dict into a chat-friendly string."""
    number = quote.get("number", "?")
    text = quote.get("text", "")
    quotee = quote.get("quotee", {})
    name = quotee.get("display_name", quotee.get("username", "???"))
    year = quote.get("year", "")
    year_str = f" [{year}]" if year else ""
    return f'Quote #{number}: "{text}" — {name}{year_str}'


class QuoteHandler(SkillHandler):
    """!quote — Retrieve, search, and add quotes via Synthfunc."""

    name = "quote"

    async def handle(self, payload, args, skill, bot):
        chatter_name = (
            payload.chatter.display_name if payload.chatter else "someone"
        )

        if not args:
            await self._random(payload, bot, chatter_name)
            return

        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()
        sub_args = parts[1] if len(parts) > 1 else ""

        if subcommand.isdigit():
            await self._by_number(payload, bot, chatter_name, int(subcommand))
        elif subcommand == "search":
            await self._search(payload, bot, chatter_name, sub_args)
        elif subcommand == "user":
            await self._by_user(payload, bot, chatter_name, sub_args)
        elif subcommand == "add":
            await self._add(payload, bot, chatter_name, sub_args)
        elif subcommand == "latest":
            await self._latest(payload, bot, chatter_name)
        elif subcommand == "stats":
            await self._stats(payload, bot, chatter_name, sub_args)
        else:
            await self._random(payload, bot, chatter_name)

    async def _random(self, payload, bot, chatter_name):
        quote = await get_random_quote()
        if not quote:
            await send_reply(
                payload, "No quotes found.", bot_id=bot.bot_id
            )
            return
        await send_reply(payload, _format_quote(quote), bot_id=bot.bot_id)

    async def _by_number(self, payload, bot, chatter_name, number):
        quote = await get_quote_by_number(number)
        if not quote:
            await send_reply(
                payload,
                f"Quote #{number} not found.",
                bot_id=bot.bot_id,
            )
            return
        await send_reply(payload, _format_quote(quote), bot_id=bot.bot_id)

    async def _search(self, payload, bot, chatter_name, query):
        if not query:
            await send_reply(
                payload,
                "Usage: !quote search <text>",
                bot_id=bot.bot_id,
            )
            return

        result = await search_quotes(query, limit=3)
        if not result or not result.get("quotes"):
            await send_reply(
                payload,
                f'No quotes found matching "{query}".',
                bot_id=bot.bot_id,
            )
            return

        total = result.get("total_matches", 0)
        quotes = result["quotes"]
        first = _format_quote(quotes[0])
        suffix = f" ({total} total matches)" if total > 1 else ""
        await send_reply(
            payload, f"{first}{suffix}", bot_id=bot.bot_id
        )

    async def _by_user(self, payload, bot, chatter_name, username):
        if not username:
            await send_reply(
                payload,
                "Usage: !quote user <username>",
                bot_id=bot.bot_id,
            )
            return

        username = username.lstrip("@")
        result = await get_quotes_by_user(username, limit=1, random=True)
        if not result or not result.get("quotes"):
            await send_reply(
                payload,
                f"No quotes found for {username}.",
                bot_id=bot.bot_id,
            )
            return

        total = result.get("total_matches", 0)
        quote = result["quotes"][0]
        formatted = _format_quote(quote)
        suffix = f" ({total} total)" if total > 1 else ""
        await send_reply(
            payload, f"{formatted}{suffix}", bot_id=bot.bot_id
        )

    async def _add(self, payload, bot, chatter_name, args_str):
        if not args_str:
            await send_reply(
                payload,
                "Usage: !quote add @user Something they said",
                bot_id=bot.bot_id,
            )
            return

        parts = args_str.split(maxsplit=1)
        if len(parts) < 2:
            await send_reply(
                payload,
                "Usage: !quote add @user Something they said",
                bot_id=bot.bot_id,
            )
            return

        quotee = parts[0].lstrip("@")
        text = parts[1]

        quote = await create_quote(text, quotee, chatter_name)
        if not quote:
            await send_reply(
                payload,
                "Failed to add quote.",
                bot_id=bot.bot_id,
            )
            return

        number = quote.get("number", "?")
        await send_reply(
            payload,
            f"Quote #{number} added!",
            bot_id=bot.bot_id,
        )

    async def _latest(self, payload, bot, chatter_name):
        quote = await get_latest_quote()
        if not quote:
            await send_reply(
                payload, "No quotes found.", bot_id=bot.bot_id
            )
            return
        await send_reply(payload, _format_quote(quote), bot_id=bot.bot_id)

    async def _stats(self, payload, bot, chatter_name, username):
        if not username:
            username = chatter_name

        username = username.lstrip("@")
        stats = await get_quote_stats(username)
        if not stats or stats.get("total_quotes", 0) == 0:
            await send_reply(
                payload,
                f"No quote stats found for {username}.",
                bot_id=bot.bot_id,
            )
            return

        total = stats["total_quotes"]
        first_year = stats.get("first_quote_year", "?")
        last_year = stats.get("last_quote_year", "?")
        avg_len = int(stats.get("average_length", 0))
        await send_reply(
            payload,
            f"{username}: {total} quotes ({first_year}-{last_year}), "
            f"avg length {avg_len} chars",
            bot_id=bot.bot_id,
        )


register_skill(QuoteHandler())
