from __future__ import annotations

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import TwitchProfile


@pytest.fixture()
def client(db):
    return Client()


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
        assert User.objects.filter(username="twitch_38981465").exists()
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


class TestDashboardLogout:
    def test_logout_redirects(self, client):
        user = User.objects.create_user(username="testuser", password="pass")
        client.login(username="testuser", password="pass")

        response = client.get("/auth/logout/")
        assert response.status_code == 302
        assert response.url == "/"
