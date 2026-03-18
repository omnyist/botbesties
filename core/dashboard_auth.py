from __future__ import annotations

import json
import logging
import secrets
from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import auth
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect

from .models import TwitchProfile

logger = logging.getLogger(__name__)

TWITCH_AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"

DASHBOARD_SCOPES = ["user:read:email"]


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
        "scope": " ".join(DASHBOARD_SCOPES),
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

    logger.info("Dashboard login: %s (%s)", twitch_display_name, twitch_id)
    return HttpResponseRedirect("/")


async def dashboard_logout(request: HttpRequest) -> HttpResponse:
    """Log out and redirect to the login page."""
    await sync_to_async(auth.logout)(request)
    return HttpResponseRedirect("/")


async def _get_or_create_user(
    twitch_id: str,
    twitch_username: str,
    twitch_display_name: str,
    twitch_avatar: str,
) -> tuple:
    """Find or create a Django User + TwitchProfile for the given Twitch account."""
    from django.contrib.auth.models import User
    from django.db import IntegrityError

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

    try:
        user = await sync_to_async(User.objects.create_user)(
            username=f"twitch_{twitch_id}",
            password=None,
        )

        profile = await sync_to_async(TwitchProfile.objects.create)(
            user=user,
            twitch_id=twitch_id,
            twitch_username=twitch_username,
            twitch_display_name=twitch_display_name,
            twitch_avatar=twitch_avatar,
        )

        return user, profile
    except IntegrityError:
        profile = await sync_to_async(
            TwitchProfile.objects.select_related("user").get
        )(twitch_id=twitch_id)
        return profile.user, profile
