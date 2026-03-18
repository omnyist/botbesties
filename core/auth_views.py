from __future__ import annotations

import json
import logging
import secrets
import uuid
from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
from datetime import timedelta

import httpx
from django.conf import settings
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.utils import timezone

from .models import Bot
from .models import Channel
from .scopes import BOT_SCOPES
from .scopes import CHANNEL_SCOPES

logger = logging.getLogger(__name__)

TWITCH_AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def setup_page(request: HttpRequest, bot_id: uuid.UUID) -> HttpResponse:
    """Simple setup page with connect buttons for a bot and its channels."""
    bot = get_object_or_404(Bot, id=bot_id)
    channels = bot.channels.all()

    return render(
        request,
        "core/setup.html",
        {
            "bot": bot,
            "channels": channels,
        },
    )


def twitch_connect(request: HttpRequest) -> HttpResponse:
    """Redirect to Twitch OAuth authorize URL."""
    connect_type = request.GET.get("type")
    bot_id = request.GET.get("bot_id")
    channel_id = request.GET.get("channel_id")

    if connect_type not in ("bot", "channel"):
        return HttpResponseBadRequest("Invalid connection type.")

    if not bot_id:
        return HttpResponseBadRequest("Missing bot_id.")

    if connect_type == "channel" and not channel_id:
        return HttpResponseBadRequest("Missing channel_id.")

    scopes = BOT_SCOPES if connect_type == "bot" else CHANNEL_SCOPES

    state_data = {
        "type": connect_type,
        "bot_id": bot_id,
        "nonce": secrets.token_urlsafe(16),
    }
    if channel_id:
        state_data["channel_id"] = channel_id

    state = urlsafe_b64encode(json.dumps(state_data).encode()).decode()

    redirect_uri = request.build_absolute_uri("/setup/callback/")

    params = {
        "client_id": settings.TWITCH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return HttpResponseRedirect(f"{TWITCH_AUTHORIZE_URL}?{query}")


async def twitch_callback(request: HttpRequest) -> HttpResponse:
    """Handle Twitch OAuth callback and store tokens."""
    code = request.GET.get("code")
    state_raw = request.GET.get("state")
    error = request.GET.get("error")

    if error:
        logger.error("Twitch OAuth error: %s - %s", error, request.GET.get("error_description"))
        return HttpResponseBadRequest(f"Twitch authorization failed: {error}")

    if not code or not state_raw:
        return HttpResponseBadRequest("Missing authorization code or state.")

    try:
        state_data = json.loads(urlsafe_b64decode(state_raw))
    except (json.JSONDecodeError, Exception):
        return HttpResponseBadRequest("Invalid state parameter.")

    connect_type = state_data.get("type")
    bot_id = state_data.get("bot_id")
    channel_id = state_data.get("channel_id")

    redirect_uri = request.build_absolute_uri("/setup/callback/")

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            TWITCH_TOKEN_URL,
            data={
                "client_id": settings.TWITCH_CLIENT_ID,
                "client_secret": settings.TWITCH_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

    if token_response.status_code != 200:
        logger.error("Token exchange failed: %s", token_response.text)
        return HttpResponseBadRequest("Failed to exchange authorization code.")

    token_data = token_response.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    if connect_type == "bot":
        from asgiref.sync import sync_to_async

        bot = await sync_to_async(Bot.objects.get)(id=bot_id)
        bot.access_token = access_token
        bot.refresh_token = refresh_token
        bot.token_expires_at = expires_at
        await sync_to_async(bot.save)()

        logger.info("Bot token saved for %s", bot.name)

    elif connect_type == "channel":
        from asgiref.sync import sync_to_async

        from .synthfunc import save_token as synthfunc_save_token

        channel = await sync_to_async(Channel.objects.get)(id=channel_id)

        # Save locally as fallback cache
        channel.owner_access_token = access_token
        channel.owner_refresh_token = refresh_token
        channel.owner_token_expires_at = expires_at
        await sync_to_async(channel.save)()

        logger.info(
            "Channel owner token saved for #%s", channel.twitch_channel_name
        )

        # Push to Synthfunc as the source of truth
        try:
            result = await synthfunc_save_token(
                user_id=channel.twitch_channel_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )
            if result:
                logger.info(
                    "Channel owner token pushed to Synthfunc for #%s",
                    channel.twitch_channel_name,
                )
            else:
                logger.warning(
                    "Failed to push channel owner token to Synthfunc for #%s",
                    channel.twitch_channel_name,
                )
        except Exception:
            logger.exception(
                "Unexpected error pushing token to Synthfunc for #%s",
                channel.twitch_channel_name,
            )

    return HttpResponseRedirect(f"/setup/{bot_id}/")
