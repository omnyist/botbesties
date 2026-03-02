from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

from core.twitch import refresh_channel_token
from core.twitch import twitch_request


def _mock_httpx_response(status_code=200, json_data=None, text=""):
    """Create a mock httpx response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = text
    return response


def _make_mock_channel(
    access_token="fake_token",
    refresh_token="fake_refresh",
    channel_name="testchannel",
):
    """Create a mock Channel object."""
    channel = MagicMock()
    channel.owner_access_token = access_token
    channel.owner_refresh_token = refresh_token
    channel.twitch_channel_name = channel_name
    channel.save = MagicMock()
    return channel


class TestRefreshChannelToken:
    async def test_successful_refresh_updates_channel(self):
        channel = _make_mock_channel()

        token_response = _mock_httpx_response(
            json_data={
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "expires_in": 14400,
            }
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = token_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.twitch.httpx.AsyncClient", return_value=mock_client):
            result = await refresh_channel_token(channel)

        assert result is True
        assert channel.owner_access_token == "new_access_token"
        assert channel.owner_refresh_token == "new_refresh_token"
        channel.save.assert_called_once()

    async def test_failed_refresh_returns_false(self):
        channel = _make_mock_channel()

        token_response = _mock_httpx_response(
            status_code=400,
            json_data={"message": "Invalid refresh token"},
            text="Invalid refresh token",
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = token_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.twitch.httpx.AsyncClient", return_value=mock_client):
            result = await refresh_channel_token(channel)

        assert result is False
        assert channel.owner_access_token == "fake_token"

    async def test_no_refresh_token_returns_false(self):
        channel = _make_mock_channel(refresh_token="")

        result = await refresh_channel_token(channel)

        assert result is False

    async def test_preserves_refresh_token_if_not_returned(self):
        channel = _make_mock_channel(refresh_token="original_refresh")

        token_response = _mock_httpx_response(
            json_data={
                "access_token": "new_access_token",
                "expires_in": 14400,
            }
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = token_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.twitch.httpx.AsyncClient", return_value=mock_client):
            result = await refresh_channel_token(channel)

        assert result is True
        assert channel.owner_refresh_token == "original_refresh"

    async def test_sends_correct_payload(self):
        channel = _make_mock_channel(refresh_token="my_refresh_token")

        token_response = _mock_httpx_response(
            json_data={
                "access_token": "new_token",
                "refresh_token": "new_refresh",
                "expires_in": 3600,
            }
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = token_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "core.twitch.httpx.AsyncClient", return_value=mock_client
            ),
            patch("core.twitch.settings") as mock_settings,
        ):
            mock_settings.TWITCH_CLIENT_ID = "test_client_id"
            mock_settings.TWITCH_CLIENT_SECRET = "test_client_secret"
            await refresh_channel_token(channel)

        call_kwargs = mock_client.post.call_args
        post_data = call_kwargs[1]["data"]
        assert post_data["grant_type"] == "refresh_token"
        assert post_data["refresh_token"] == "my_refresh_token"
        assert post_data["client_id"] == "test_client_id"
        assert post_data["client_secret"] == "test_client_secret"


class TestTwitchRequest:
    async def test_successful_request(self):
        channel = _make_mock_channel()

        api_response = _mock_httpx_response(
            json_data={"data": [{"id": "123"}]}
        )

        mock_client = AsyncMock()
        mock_client.request.return_value = api_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("core.twitch.httpx.AsyncClient", return_value=mock_client):
            result = await twitch_request(
                channel,
                "GET",
                "https://api.twitch.tv/helix/channels/followers",
                params={"broadcaster_id": "99999"},
            )

        assert result is not None
        assert result.status_code == 200

    async def test_no_token_returns_none(self):
        channel = _make_mock_channel(access_token="")

        result = await twitch_request(
            channel,
            "GET",
            "https://api.twitch.tv/helix/channels/followers",
        )

        assert result is None

    async def test_401_triggers_refresh_and_retry(self):
        channel = _make_mock_channel()

        unauthorized_response = _mock_httpx_response(status_code=401)
        success_response = _mock_httpx_response(
            json_data={"data": [{"id": "123"}]}
        )

        # First call returns 401, second call (after refresh) returns 200
        mock_client = AsyncMock()
        mock_client.request.side_effect = [
            unauthorized_response,
            success_response,
        ]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "core.twitch.httpx.AsyncClient", return_value=mock_client
            ),
            patch(
                "core.twitch.refresh_channel_token",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_refresh,
        ):
            channel.owner_access_token = "refreshed_token"
            result = await twitch_request(
                channel,
                "GET",
                "https://api.twitch.tv/helix/channels/followers",
            )

        assert result is not None
        assert result.status_code == 200
        mock_refresh.assert_called_once_with(channel)
        assert mock_client.request.call_count == 2

    async def test_401_with_failed_refresh_returns_none(self):
        channel = _make_mock_channel()

        unauthorized_response = _mock_httpx_response(status_code=401)

        mock_client = AsyncMock()
        mock_client.request.return_value = unauthorized_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "core.twitch.httpx.AsyncClient", return_value=mock_client
            ),
            patch(
                "core.twitch.refresh_channel_token",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await twitch_request(
                channel,
                "GET",
                "https://api.twitch.tv/helix/channels/followers",
            )

        assert result is None

    async def test_adds_auth_headers(self):
        channel = _make_mock_channel(access_token="my_bearer_token")

        api_response = _mock_httpx_response()

        mock_client = AsyncMock()
        mock_client.request.return_value = api_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "core.twitch.httpx.AsyncClient", return_value=mock_client
            ),
            patch("core.twitch.settings") as mock_settings,
        ):
            mock_settings.TWITCH_CLIENT_ID = "test_client_id"
            await twitch_request(
                channel, "GET", "https://api.twitch.tv/helix/test"
            )

        call_kwargs = mock_client.request.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["Authorization"] == "Bearer my_bearer_token"
        assert headers["Client-Id"] == "test_client_id"
