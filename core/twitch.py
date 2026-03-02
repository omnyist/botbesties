from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("bot")

TWITCH_API_BASE = "https://api.twitch.tv/helix"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


async def refresh_channel_token(channel) -> bool:
    """Refresh a channel owner's OAuth token.

    Updates the channel record in the database with the new tokens.
    Returns True on success, False on failure.
    """
    if not channel.owner_refresh_token:
        logger.warning(
            "No refresh token for channel #%s", channel.twitch_channel_name
        )
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TWITCH_TOKEN_URL,
                data={
                    "client_id": settings.TWITCH_CLIENT_ID,
                    "client_secret": settings.TWITCH_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": channel.owner_refresh_token,
                },
            )

        if response.status_code != 200:
            logger.error(
                "Token refresh failed for #%s: %s",
                channel.twitch_channel_name,
                response.text,
            )
            return False

        token_data = response.json()
        channel.owner_access_token = token_data["access_token"]
        channel.owner_refresh_token = token_data.get(
            "refresh_token", channel.owner_refresh_token
        )
        expires_in = token_data.get("expires_in", 3600)
        channel.owner_token_expires_at = timezone.now() + timedelta(
            seconds=expires_in
        )
        await sync_to_async(channel.save)(
            update_fields=[
                "owner_access_token",
                "owner_refresh_token",
                "owner_token_expires_at",
            ]
        )

        logger.info(
            "Refreshed owner token for #%s", channel.twitch_channel_name
        )
        return True

    except httpx.HTTPError:
        logger.exception(
            "HTTP error refreshing token for #%s",
            channel.twitch_channel_name,
        )
        return False


async def twitch_request(
    channel,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response | None:
    """Make an authenticated Twitch API request with automatic token refresh.

    On a 401 response, attempts to refresh the channel owner's token
    and retries the request once. Returns the response on success,
    or None if both attempts fail.
    """
    if not channel.owner_access_token:
        return None

    headers = {
        "Authorization": f"Bearer {channel.owner_access_token}",
        "Client-Id": settings.TWITCH_CLIENT_ID,
    }
    kwargs.setdefault("headers", {}).update(headers)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, **kwargs)

        if response.status_code != 401:
            return response

        # Token expired — attempt refresh and retry.
        logger.info(
            "Got 401 for #%s, attempting token refresh...",
            channel.twitch_channel_name,
        )

        refreshed = await refresh_channel_token(channel)
        if not refreshed:
            return None

        # Retry with the new token.
        kwargs["headers"]["Authorization"] = (
            f"Bearer {channel.owner_access_token}"
        )

        async with httpx.AsyncClient() as client:
            return await client.request(method, url, **kwargs)

    except httpx.HTTPError:
        logger.exception(
            "HTTP error during Twitch request to %s for #%s",
            url,
            channel.twitch_channel_name,
        )
        return None
