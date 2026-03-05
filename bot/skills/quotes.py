"""!quote — Quote commands powered by Synthfunc.

Usage:
    !quote                              — Random quote
    !quote 42                           — Quote by number
    !quote search fish                  — Search quotes by text
    !quote user bryan                   — Quotes by a specific person
    !quote add "Something funny" ~ @user — Add a new quote
    !quote latest                       — Most recent quote
    !quote stats bryan                  — Quote stats for a user
"""

from __future__ import annotations

import logging
import re

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
    """Format a quote dict into Elsydeon-style chat string.

    Format: "text" ~ Name (#number, year, Game)
    Game is only included when present.
    """
    number = quote.get("number", "?")
    text = quote.get("text", "")
    quotee = quote.get("quotee", {})
    name = quotee.get("display_name", quotee.get("username", "???"))
    game = quote.get("game")
    year = quote.get("year")

    # Build metadata: (#number, year, Game) or (#number, year) or (#number)
    parts = [f"#{number}"]
    if year:
        parts.append(str(year))
    if game:
        parts.append(game)
    meta = ", ".join(parts)

    return f'"{text}" ~ {name} ({meta})'


class QuoteHandler(SkillHandler):
    """!quote — Retrieve, search, and add quotes via Synthfunc."""

    name = "quote"

    async def handle(self, payload, args, skill, bot):
        tenant_slug = skill.channel.twitch_channel_name
        chatter_name = (
            payload.chatter.display_name if payload.chatter else "someone"
        )

        if not args:
            await self._random(payload, bot, chatter_name, tenant_slug)
            return

        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()
        sub_args = parts[1] if len(parts) > 1 else ""

        if subcommand.isdigit():
            await self._by_number(
                payload, bot, chatter_name, int(subcommand), tenant_slug
            )
        elif subcommand == "search":
            await self._search(payload, bot, chatter_name, sub_args, tenant_slug)
        elif subcommand == "user":
            await self._by_user(payload, bot, chatter_name, sub_args, tenant_slug)
        elif subcommand == "add":
            await self._add(payload, bot, chatter_name, sub_args, tenant_slug)
        elif subcommand == "latest":
            await self._latest(payload, bot, chatter_name, tenant_slug)
        elif subcommand == "stats":
            await self._stats(payload, bot, chatter_name, sub_args, tenant_slug)
        else:
            await self._random(payload, bot, chatter_name, tenant_slug)

    async def _random(self, payload, bot, chatter_name, tenant_slug):
        quote = await get_random_quote(tenant_slug)
        if not quote:
            await send_reply(
                payload, "No quotes found.", bot_id=bot.bot_id
            )
            return
        await send_reply(
            payload,
            f"I found this quote: {_format_quote(quote)}",
            bot_id=bot.bot_id,
        )

    async def _by_number(self, payload, bot, chatter_name, number, tenant_slug):
        quote = await get_quote_by_number(number, tenant_slug)
        if not quote:
            await send_reply(
                payload,
                f"Quote #{number} not found.",
                bot_id=bot.bot_id,
            )
            return
        await send_reply(
            payload,
            f"I found this quote: {_format_quote(quote)}",
            bot_id=bot.bot_id,
        )

    async def _search(self, payload, bot, chatter_name, query, tenant_slug):
        if not query:
            await send_reply(
                payload,
                "Usage: !quote search <text>",
                bot_id=bot.bot_id,
            )
            return

        result = await search_quotes(query, tenant_slug, limit=1, random=True)
        if not result or not result.get("quotes"):
            await send_reply(
                payload,
                f'No quotes found containing "{query}"',
                bot_id=bot.bot_id,
            )
            return

        total = result.get("total_matches", 0)
        formatted = _format_quote(result["quotes"][0])
        if total == 1:
            await send_reply(
                payload,
                f"I found this quote: {formatted}",
                bot_id=bot.bot_id,
            )
        else:
            await send_reply(
                payload,
                f'I found {total} quotes with "{query}". '
                f"Here's one: {formatted}",
                bot_id=bot.bot_id,
            )

    async def _by_user(self, payload, bot, chatter_name, username, tenant_slug):
        if not username:
            await send_reply(
                payload,
                "Usage: !quote user <username>",
                bot_id=bot.bot_id,
            )
            return

        username = username.lstrip("@")
        result = await get_quotes_by_user(
            username, tenant_slug, limit=1, random=True
        )
        if not result or not result.get("quotes"):
            await send_reply(
                payload,
                f'No quotes found from "{username}".',
                bot_id=bot.bot_id,
            )
            return

        total = result.get("total_matches", 0)
        formatted = _format_quote(result["quotes"][0])
        if total == 1:
            await send_reply(
                payload,
                f"I found this quote from {username}: {formatted}",
                bot_id=bot.bot_id,
            )
        else:
            await send_reply(
                payload,
                f"I found {total} quotes from {username}. "
                f"Here's one: {formatted}",
                bot_id=bot.bot_id,
            )

    # Matches: "quote text here" ~ @username
    ADD_PATTERN = re.compile(r'"([^"]*?)"\s*~\s*@([A-Za-z0-9_]+)')

    async def _add(self, payload, bot, chatter_name, args_str, tenant_slug):
        if not args_str:
            await send_reply(
                payload,
                'Usage: !quote add "Something they said" ~ @username',
                bot_id=bot.bot_id,
            )
            return

        match = self.ADD_PATTERN.search(args_str)
        if not match:
            await send_reply(
                payload,
                'I has OCD and can\'t accept that quote. Please format it '
                'like so: "quote" ~ @username',
                bot_id=bot.bot_id,
            )
            return

        text = match.group(1)
        quotee = match.group(2)

        quote = await create_quote(text, quotee, chatter_name, tenant_slug)
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
            f"I've added quote #{number} to the database. "
            "Blame yourself or God.",
            bot_id=bot.bot_id,
        )

    async def _latest(self, payload, bot, chatter_name, tenant_slug):
        quote = await get_latest_quote(tenant_slug)
        if not quote:
            await send_reply(
                payload, "No quotes found.", bot_id=bot.bot_id
            )
            return
        await send_reply(
            payload,
            f"I found this quote: {_format_quote(quote)}",
            bot_id=bot.bot_id,
        )

    async def _stats(self, payload, bot, chatter_name, username, tenant_slug):
        if not username:
            username = chatter_name

        username = username.lstrip("@")
        stats = await get_quote_stats(username, tenant_slug)
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
