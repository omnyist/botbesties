"""Async client for Synthfunc's REST API.

Provides typed functions for each Synthfunc endpoint that the bot
needs — quotes, campaigns, members, and stream status.

Usage:
    from core.synthfunc import get_random_quote, search_quotes

    quote = await get_random_quote()
    results = await search_quotes("fish")
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger("bot")


def _headers() -> dict[str, str]:
    return {"X-API-Key": settings.SYNTHFUNC_API_KEY}


async def _get(path: str, params: dict[str, Any] | None = None) -> dict | list | None:
    """Make a GET request to Synthfunc."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.SYNTHFUNC_API_URL}{path}",
                headers=_headers(),
                params=params,
                timeout=10.0,
            )

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            logger.error(
                "Synthfunc GET %s failed: %s %s",
                path,
                response.status_code,
                response.text,
            )
            return None

        return response.json()

    except httpx.HTTPError:
        logger.exception("HTTP error during Synthfunc GET %s", path)
        return None


async def _post(path: str, data: dict[str, Any]) -> dict | None:
    """Make a POST request to Synthfunc."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.SYNTHFUNC_API_URL}{path}",
                headers=_headers(),
                json=data,
                timeout=10.0,
            )

        if response.status_code not in (200, 201):
            logger.error(
                "Synthfunc POST %s failed: %s %s",
                path,
                response.status_code,
                response.text,
            )
            return None

        return response.json()

    except httpx.HTTPError:
        logger.exception("HTTP error during Synthfunc POST %s", path)
        return None


# --- Quotes ---


async def get_random_quote() -> dict | None:
    """Get a single random quote."""
    result = await _get("/quotes/random", {"limit": 1})
    if result and isinstance(result, list) and len(result) > 0:
        return result[0]
    return None


async def get_quote_by_number(number: int) -> dict | None:
    """Get a specific quote by its number."""
    return await _get(f"/quotes/{number}")


async def search_quotes(
    query: str, limit: int = 5, random: bool = False
) -> dict | None:
    """Search quotes by text. Returns {quotes: [...], total_matches: int}."""
    return await _get(
        "/quotes/search", {"q": query, "limit": limit, "random": random}
    )


async def get_quotes_by_user(
    username: str, limit: int = 5, random: bool = False
) -> dict | None:
    """Get quotes by a specific user. Returns {quotes: [...], total_matches: int}."""
    return await _get(
        f"/quotes/by-user/{username}", {"limit": limit, "random": random}
    )


async def get_latest_quote() -> dict | None:
    """Get the most recent quote."""
    result = await _get("/quotes/latest", {"limit": 1})
    if result and isinstance(result, list) and len(result) > 0:
        return result[0]
    return None


async def get_quote_stats(username: str) -> dict | None:
    """Get quote statistics for a user."""
    return await _get(f"/quotes/stats/{username}")


async def create_quote(
    text: str,
    quotee_username: str,
    quoter_username: str,
    game: str | None = None,
) -> dict | None:
    """Create a new quote."""
    data = {
        "text": text,
        "quotee_username": quotee_username,
        "quoter_username": quoter_username,
    }
    if game:
        data["game"] = game
    return await _post("/quotes/", data)


# --- Wallets ---


async def get_wallet(twitch_id: str, username: str | None = None) -> dict | None:
    """Get a wallet by Twitch ID, with optional username for reconciliation."""
    params = {"username": username} if username else None
    return await _get(f"/wallets/{twitch_id}", params)


async def get_wallet_leaderboard(
    limit: int = 10, sort_by: str = "balance"
) -> list | None:
    """Get top wallets by balance or minutes."""
    return await _get("/wallets/leaderboard", {"limit": limit, "sort_by": sort_by})


# --- Campaigns ---


async def get_active_campaign() -> dict | None:
    """Get the currently active campaign with metrics and milestones."""
    return await _get("/campaigns/active")


async def get_campaign_metrics(campaign_id: str) -> dict | None:
    """Get metrics for a specific campaign."""
    return await _get(f"/campaigns/{campaign_id}/metrics")


async def get_gift_leaderboard(limit: int = 10) -> list | None:
    """Get the gift leaderboard for the active campaign."""
    return await _get("/campaigns/active/gifts/leaderboard", {"limit": limit})


# --- Members ---


async def get_member(twitch_id: str) -> dict | None:
    """Get or create a member by Twitch ID."""
    return await _get(f"/members/{twitch_id}")


async def create_member(
    display_name: str,
    username: str | None = None,
    twitch_id: str | None = None,
) -> dict | None:
    """Create a new member."""
    data: dict[str, Any] = {"display_name": display_name}
    if username:
        data["username"] = username
    if twitch_id:
        data["twitch_id"] = twitch_id
    return await _post("/members/", data)


# --- Streams ---


async def get_stream_status() -> dict | None:
    """Get current broadcaster stream status."""
    return await _get("/streams/status/")


# --- Tokens ---


async def save_token(
    user_id: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_in: int = 3600,
) -> dict | None:
    """Push an OAuth token to Synthfunc for centralized storage."""
    return await _post(
        "/authentication/tokens/",
        {
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
        },
    )


async def get_token(user_id: str) -> dict | None:
    """Fetch an OAuth token from Synthfunc."""
    return await _get(f"/authentication/tokens/{user_id}")
