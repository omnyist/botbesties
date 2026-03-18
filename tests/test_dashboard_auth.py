from __future__ import annotations

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import Bot
from core.models import Channel
from core.models import TwitchProfile


@pytest.fixture()
def client(db):
    return Client()


@pytest.fixture()
def test_bot(db):
    return Bot.objects.create(
        name="TestBot",
        twitch_user_id="66977097",
        twitch_username="testbot",
    )


@pytest.fixture()
def test_channel(test_bot):
    return Channel.objects.create(
        bot=test_bot,
        twitch_channel_id="38981465",
        twitch_channel_name="avalonstar",
        is_active=True,
    )


TWITCH_USER_DATA = {
    "data": [
        {
            "id": "38981465",
            "login": "avalonstar",
            "display_name": "Avalonstar",
            "profile_image_url": "https://example.com/avatar.png",
        }
    ]
}


def _build_state(nonce: str) -> str:
    from base64 import urlsafe_b64encode

    state_data = {"nonce": nonce, "purpose": "dashboard"}
    return urlsafe_b64encode(json.dumps(state_data).encode()).decode()


def _mock_httpx(token_data=None, user_data=None):
    """Return a patched httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = token_data or {
        "access_token": "test-token",
        "refresh_token": "test-refresh",
        "expires_in": 3600,
    }

    user_response = MagicMock()
    user_response.status_code = 200
    user_response.json.return_value = user_data or TWITCH_USER_DATA

    mock_client.post.return_value = token_response
    mock_client.get.return_value = user_response

    return mock_client


class TestTwitchLogin:
    def test_redirects_to_twitch(self, client):
        response = client.get("/auth/twitch/login/")
        assert response.status_code == 302
        assert "id.twitch.tv/oauth2/authorize" in response.url

    def test_requests_channel_scopes(self, client):
        response = client.get("/auth/twitch/login/")
        assert "moderator%3Amanage%3Abanned_users" in response.url
        assert "channel%3Aread%3Asubscriptions" in response.url

    def test_state_contains_nonce(self, client):
        response = client.get("/auth/twitch/login/")
        assert "state=" in response.url

    def test_stores_nonce_in_session(self, client):
        client.get("/auth/twitch/login/")
        session = client.session
        assert "dashboard_oauth_nonce" in session


class TestTwitchCallback:
    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_creates_user_on_first_login(self, mock_client_cls, client):
        nonce = "test-nonce-123"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        response = client.get(
            f"/auth/twitch/callback/?code=test-code&state={state}"
        )

        assert response.status_code == 302
        assert response.url == "/"
        assert User.objects.filter(username="avalonstar").exists()
        assert TwitchProfile.objects.filter(twitch_id="38981465").exists()

    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_updates_profile_on_repeat_login(self, mock_client_cls, client):
        user = User.objects.create_user(username="avalonstar")
        TwitchProfile.objects.create(
            user=user,
            twitch_id="38981465",
            twitch_username="avalonstar",
            twitch_display_name="OldName",
            twitch_avatar="",
        )

        nonce = "test-nonce-456"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        response = client.get(
            f"/auth/twitch/callback/?code=test-code&state={state}"
        )

        assert response.status_code == 302
        profile = TwitchProfile.objects.get(twitch_id="38981465")
        assert profile.twitch_display_name == "Avalonstar"
        assert profile.twitch_avatar == "https://example.com/avatar.png"

    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_denies_user_not_in_allowlist(self, mock_client_cls, client):
        nonce = "test-nonce-789"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx(
            user_data={
                "data": [
                    {
                        "id": "99999999",
                        "login": "randomuser",
                        "display_name": "RandomUser",
                        "profile_image_url": "",
                    }
                ]
            },
        )

        state = _build_state(nonce)

        with patch(
            "core.dashboard_auth.settings"
        ) as mock_settings:
            mock_settings.TWITCH_CLIENT_ID = "test"
            mock_settings.TWITCH_CLIENT_SECRET = "test"
            mock_settings.DASHBOARD_ALLOWED_TWITCH_IDS = ["38981465"]
            response = client.get(
                f"/auth/twitch/callback/?code=test-code&state={state}"
            )

        assert response.status_code == 400

    def test_rejects_missing_code(self, client):
        response = client.get("/auth/twitch/callback/?state=abc")
        assert response.status_code == 400

    def test_rejects_invalid_state(self, client):
        response = client.get(
            "/auth/twitch/callback/?code=test&state=invalid"
        )
        assert response.status_code == 400

    def test_rejects_mismatched_nonce(self, client):
        session = client.session
        session["dashboard_oauth_nonce"] = "correct-nonce"
        session.save()

        state = _build_state("wrong-nonce")
        response = client.get(
            f"/auth/twitch/callback/?code=test&state={state}"
        )
        assert response.status_code == 400

    def test_reports_oauth_error(self, client):
        response = client.get(
            "/auth/twitch/callback/?error=access_denied"
            "&error_description=User+denied"
        )
        assert response.status_code == 400


class TestChannelTokenStorage:
    @patch("core.dashboard_auth._update_channel_tokens")
    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_login_calls_update_channel_tokens(
        self, mock_client_cls, mock_update, client
    ):
        """Login triggers channel token update with the OAuth tokens."""
        mock_update.return_value = None

        nonce = "test-nonce-tokens"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        response = client.get(
            f"/auth/twitch/callback/?code=test-code&state={state}"
        )

        assert response.status_code == 302
        mock_update.assert_called_once_with(
            twitch_id="38981465",
            access_token="test-token",
            refresh_token="test-refresh",
            expires_in=3600,
        )

    @patch("core.synthfunc.save_token", new_callable=AsyncMock)
    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_stores_tokens_on_channel(
        self, mock_client_cls, mock_synthfunc, client, test_channel
    ):
        """Login stores OAuth tokens on matching Channel records."""
        mock_synthfunc.return_value = {"status": "ok"}

        nonce = "test-nonce-channel"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        response = client.get(
            f"/auth/twitch/callback/?code=test-code&state={state}"
        )

        assert response.status_code == 302
        test_channel.refresh_from_db()
        assert test_channel.owner_access_token == "test-token"
        assert test_channel.owner_refresh_token == "test-refresh"
        assert test_channel.owner_token_expires_at is not None

    @patch("core.synthfunc.save_token", new_callable=AsyncMock)
    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_pushes_tokens_to_synthfunc(
        self, mock_client_cls, mock_synthfunc, client, test_channel
    ):
        """Login pushes tokens to Synthfunc as source of truth."""
        mock_synthfunc.return_value = {"status": "ok"}

        nonce = "test-nonce-synth"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        client.get(f"/auth/twitch/callback/?code=test-code&state={state}")

        mock_synthfunc.assert_called_once_with(
            user_id="38981465",
            access_token="test-token",
            refresh_token="test-refresh",
            expires_in=3600,
        )

    @patch("core.synthfunc.save_token", new_callable=AsyncMock)
    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_updates_all_channels_for_owner(
        self, mock_client_cls, mock_synthfunc, client, test_bot
    ):
        """Login updates tokens on all active channels the user owns."""
        mock_synthfunc.return_value = {"status": "ok"}

        bot2 = Bot.objects.create(
            name="TestBot2",
            twitch_user_id="149214941",
            twitch_username="testbot2",
        )
        ch1 = Channel.objects.create(
            bot=test_bot,
            twitch_channel_id="38981465",
            twitch_channel_name="avalonstar",
            is_active=True,
        )
        ch2 = Channel.objects.create(
            bot=bot2,
            twitch_channel_id="38981465",
            twitch_channel_name="avalonstar",
            is_active=True,
        )
        bot3 = Bot.objects.create(
            name="TestBot3",
            twitch_user_id="99999999",
            twitch_username="testbot3",
        )
        Channel.objects.create(
            bot=bot3,
            twitch_channel_id="38981465",
            twitch_channel_name="avalonstar",
            is_active=False,
        )

        nonce = "test-nonce-multi"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        client.get(f"/auth/twitch/callback/?code=test-code&state={state}")

        ch1.refresh_from_db()
        ch2.refresh_from_db()
        assert ch1.owner_access_token == "test-token"
        assert ch2.owner_access_token == "test-token"

        inactive = Channel.objects.get(bot=bot3, is_active=False)
        assert inactive.owner_access_token is None

        mock_synthfunc.assert_called_once()

    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_login_succeeds_without_channels(self, mock_client_cls, client):
        """Login works when user has no channels (no token storage needed)."""
        nonce = "test-nonce-nochan"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        response = client.get(
            f"/auth/twitch/callback/?code=test-code&state={state}"
        )

        assert response.status_code == 302
        assert response.url == "/"

    @patch("core.synthfunc.save_token", new_callable=AsyncMock)
    @patch("core.dashboard_auth.httpx.AsyncClient")
    def test_synthfunc_failure_does_not_block_login(
        self, mock_client_cls, mock_synthfunc, client, test_channel
    ):
        """Login succeeds even if Synthfunc push fails."""
        mock_synthfunc.side_effect = Exception("Synthfunc down")

        nonce = "test-nonce-fail"
        session = client.session
        session["dashboard_oauth_nonce"] = nonce
        session.save()

        mock_client_cls.return_value = _mock_httpx()

        state = _build_state(nonce)
        response = client.get(
            f"/auth/twitch/callback/?code=test-code&state={state}"
        )

        assert response.status_code == 302
        assert response.url == "/"
        test_channel.refresh_from_db()
        assert test_channel.owner_access_token == "test-token"


class TestDashboardLogout:
    def test_logout_redirects(self, client):
        user = User.objects.create_user(username="testuser", password="pass")
        client.login(username="testuser", password="pass")

        response = client.get("/auth/logout/")
        assert response.status_code == 302
        assert response.url == "/"
