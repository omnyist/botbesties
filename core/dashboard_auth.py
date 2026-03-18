from __future__ import annotations

import json
import logging
import secrets
from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import auth
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.utils import timezone

from .models import Channel
from .models import TwitchProfile
from .scopes import CHANNEL_SCOPES

logger = logging.getLogger(__name__)

TWITCH_AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"


def twitch_login(request: HttpRequest) -> HttpResponse:
    """Redirect to Twitch OAuth for dashboard login."""
    nonce = secrets.token_urlsafe(16)
    state_data = {"nonce": nonce, "purpose": "dashboard"}
    state = urlsafe_b64encode(json.dumps(state_data).encode()).decode()

    request.session["dashboard_oauth_nonce"] = nonce

    redirect_uri = request.build_absolute_uri("/auth/twitch/callback/")

    params = {
        "client_id": settings.TWITCH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(CHANNEL_SCOPES),
        "state": state,
    }

    return HttpResponseRedirect(f"{TWITCH_AUTHORIZE_URL}?{urlencode(params)}")


async def twitch_callback(request: HttpRequest) -> HttpResponse:
    """Handle Twitch OAuth callback, create/update user, log in."""
    code = request.GET.get("code")
    state_raw = request.GET.get("state")
    error = request.GET.get("error")

    if error:
        logger.error(
            "Dashboard OAuth error: %s - %s",
            error,
            request.GET.get("error_description"),
        )
        return HttpResponseBadRequest(f"Twitch authorization failed: {error}")

    if not code or not state_raw:
        return HttpResponseBadRequest("Missing authorization code or state.")

    try:
        state_data = json.loads(urlsafe_b64decode(state_raw))
    except (json.JSONDecodeError, Exception):
        return HttpResponseBadRequest("Invalid state parameter.")

    if state_data.get("purpose") != "dashboard":
        return HttpResponseBadRequest("Invalid state purpose.")

    stored_nonce = await sync_to_async(request.session.pop)(
        "dashboard_oauth_nonce", None
    )
    if not stored_nonce or state_data.get("nonce") != stored_nonce:
        return HttpResponseBadRequest("Invalid state nonce.")

    redirect_uri = request.build_absolute_uri("/auth/twitch/callback/")

    # Exchange code for token.
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
        logger.error("Dashboard token exchange failed: %s", token_response.text)
        return HttpResponseBadRequest("Failed to exchange authorization code.")

    token_data = token_response.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    # Fetch Twitch user info.
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            TWITCH_USERS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Client-Id": settings.TWITCH_CLIENT_ID,
            },
        )

    if user_response.status_code != 200:
        logger.error("Failed to fetch Twitch user info: %s", user_response.text)
        return HttpResponseBadRequest("Failed to fetch user info from Twitch.")

    twitch_users = user_response.json().get("data", [])
    if not twitch_users:
        return HttpResponseBadRequest("No user data returned from Twitch.")

    twitch_user = twitch_users[0]
    twitch_id = twitch_user["id"]
    twitch_username = twitch_user["login"]
    twitch_display_name = twitch_user["display_name"]
    twitch_avatar = twitch_user.get("profile_image_url", "")

    # Check allowlist.
    allowed_ids = getattr(settings, "DASHBOARD_ALLOWED_TWITCH_IDS", [])
    if allowed_ids and twitch_id not in allowed_ids:
        logger.warning(
            "Dashboard login denied for %s (%s) — not in allowlist",
            twitch_display_name,
            twitch_id,
        )
        return HttpResponseBadRequest("You are not authorized to access the dashboard.")

    # Get or create Django User + TwitchProfile.
    user, profile = await _get_or_create_user(
        twitch_id=twitch_id,
        twitch_username=twitch_username,
        twitch_display_name=twitch_display_name,
        twitch_avatar=twitch_avatar,
    )

    await sync_to_async(auth.login)(
        request, user, backend="django.contrib.auth.backends.ModelBackend"
    )

    # Update channel tokens for channels this user owns.
    await _update_channel_tokens(
        twitch_id=twitch_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )

    logger.info("Dashboard login: %s (%s)", twitch_display_name, twitch_id)
    return HttpResponseRedirect("/")


async def dashboard_logout(request: HttpRequest) -> HttpResponse:
    """Log out and redirect to the login page."""
    await sync_to_async(auth.logout)(request)
    return HttpResponseRedirect("/")


async def _update_channel_tokens(
    twitch_id: str,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    """Store channel owner tokens for all channels this user owns."""
    from .synthfunc import save_token as synthfunc_save_token

    expires_at = timezone.now() + timedelta(seconds=expires_in)

    channels = []
    async for channel in Channel.objects.filter(
        twitch_channel_id=twitch_id, is_active=True
    ):
        channels.append(channel)

    if not channels:
        return

    for channel in channels:
        channel.owner_access_token = access_token
        channel.owner_refresh_token = refresh_token
        channel.owner_token_expires_at = expires_at
        await sync_to_async(channel.save)(
            update_fields=["owner_access_token", "owner_refresh_token", "owner_token_expires_at"]
        )

        logger.info(
            "Channel owner token saved for #%s", channel.twitch_channel_name
        )

    # Push to Synthfunc as the source of truth.
    try:
        result = await synthfunc_save_token(
            user_id=twitch_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
        if result:
            logger.info(
                "Channel owner token pushed to Synthfunc for %s", twitch_id
            )
        else:
            logger.warning(
                "Failed to push channel owner token to Synthfunc for %s",
                twitch_id,
            )
    except Exception:
        logger.exception(
            "Unexpected error pushing token to Synthfunc for %s", twitch_id
        )


async def _get_or_create_user(
    twitch_id: str,
    twitch_username: str,
    twitch_display_name: str,
    twitch_avatar: str,
) -> tuple:
    """Find or create a Django User + TwitchProfile for the given Twitch account."""
    from django.contrib.auth.models import User

    # Existing profile? Update and return.
    try:
        profile = await sync_to_async(
            TwitchProfile.objects.select_related("user").get
        )(twitch_id=twitch_id)
        profile.twitch_username = twitch_username
        profile.twitch_display_name = twitch_display_name
        profile.twitch_avatar = twitch_avatar
        await sync_to_async(profile.save)(
            update_fields=["twitch_username", "twitch_display_name", "twitch_avatar", "updated_at"]
        )
        return profile.user, profile
    except TwitchProfile.DoesNotExist:
        pass

    # Get or create the Django User (may already exist from seed).
    def _get_or_create_django_user():
        user, created = User.objects.get_or_create(
            username=twitch_username,
            defaults={"password": "!"},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user

    user = await sync_to_async(_get_or_create_django_user)()

    profile = await sync_to_async(TwitchProfile.objects.create)(
        user=user,
        twitch_id=twitch_id,
        twitch_username=twitch_username,
        twitch_display_name=twitch_display_name,
        twitch_avatar=twitch_avatar,
    )

    return user, profile
