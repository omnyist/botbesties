from __future__ import annotations

import json
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bot.components.ads import AdAnnounce
from bot.components.ads import DEFAULT_MESSAGES
from bot.components.ads import DEFAULT_WARNING_INTERVALS
from bot.components.ads import WARNING_TOLERANCE
from bot.skills import SKILL_REGISTRY
from bot.skills import discover_skills
from bot.skills.ads import AdsHandler
from tests.conftest import MockBroadcaster
from tests.conftest import MockChatter
from tests.conftest import MockPayload


# --- Skill handler tests ---


class TestAdsRegistry:
    def test_ads_in_registry(self):
        discover_skills()
        assert "ads" in SKILL_REGISTRY
        assert isinstance(SKILL_REGISTRY["ads"], AdsHandler)


@pytest.mark.django_db(transaction=True)
class TestAdsHandler:
    @pytest.fixture()
    def handler(self):
        return AdsHandler()

    @pytest.fixture()
    def skill(self, make_skill):
        return make_skill(name="ads", config={})

    @pytest.fixture()
    def mock_bot(self):
        bot = MagicMock()
        bot.bot_id = "66977097"
        return bot

    async def test_status_when_enabled(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter())
        status_data = {
            "enabled": True,
            "next_time": "2026-03-05T23:00:00+00:00",
            "config": {"interval": 30, "duration": 90},
        }
        with patch("bot.skills.ads.get_ads_status", new_callable=AsyncMock, return_value=status_data):
            await handler.handle(payload, "", skill, mock_bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Ads: ON" in msg
        assert "30m interval" in msg
        assert "90s duration" in msg

    async def test_status_when_disabled(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter())
        status_data = {"enabled": False}
        with patch("bot.skills.ads.get_ads_status", new_callable=AsyncMock, return_value=status_data):
            await handler.handle(payload, "", skill, mock_bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Ads: OFF" in msg

    async def test_status_api_failure(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter())
        with patch("bot.skills.ads.get_ads_status", new_callable=AsyncMock, return_value=None):
            await handler.handle(payload, "", skill, mock_bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Could not fetch" in msg

    async def test_enable_as_mod(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter(moderator=True))
        with patch("bot.skills.ads.enable_ads", new_callable=AsyncMock, return_value={"ok": True}):
            await handler.handle(payload, "on", skill, mock_bot)

        # Success message comes from component, not handler
        payload.broadcaster.send_message.assert_not_called()

    async def test_enable_api_failure(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter(moderator=True))
        with patch("bot.skills.ads.enable_ads", new_callable=AsyncMock, return_value=None):
            await handler.handle(payload, "on", skill, mock_bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Failed to enable" in msg

    async def test_disable_as_broadcaster(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter(broadcaster=True))
        with patch("bot.skills.ads.disable_ads", new_callable=AsyncMock, return_value={"ok": True}):
            await handler.handle(payload, "off", skill, mock_bot)

        payload.broadcaster.send_message.assert_not_called()

    async def test_disable_api_failure(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter(broadcaster=True))
        with patch("bot.skills.ads.disable_ads", new_callable=AsyncMock, return_value=None):
            await handler.handle(payload, "off", skill, mock_bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Failed to disable" in msg

    async def test_enable_ignored_for_regular_user(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter())
        with patch("bot.skills.ads.enable_ads", new_callable=AsyncMock) as mock_enable:
            await handler.handle(payload, "on", skill, mock_bot)

        mock_enable.assert_not_called()
        payload.broadcaster.send_message.assert_not_called()

    async def test_disable_ignored_for_regular_user(self, handler, skill, mock_bot):
        payload = MockPayload(chatter=MockChatter())
        with patch("bot.skills.ads.disable_ads", new_callable=AsyncMock) as mock_disable:
            await handler.handle(payload, "off", skill, mock_bot)

        mock_disable.assert_not_called()
        payload.broadcaster.send_message.assert_not_called()

    def test_format_remaining_minutes_and_seconds(self, handler):
        from datetime import UTC
        from datetime import datetime
        from datetime import timedelta

        future = (datetime.now(UTC) + timedelta(minutes=2, seconds=30)).isoformat()
        result = handler._format_remaining(future)
        assert "2m" in result

    def test_format_remaining_seconds_only(self, handler):
        from datetime import UTC
        from datetime import datetime
        from datetime import timedelta

        future = (datetime.now(UTC) + timedelta(seconds=45)).isoformat()
        result = handler._format_remaining(future)
        assert "s" in result
        assert "m" not in result

    def test_format_remaining_none(self, handler):
        assert handler._format_remaining(None) == "unknown"

    def test_format_remaining_invalid(self, handler):
        assert handler._format_remaining("not-a-date") == "unknown"


# --- Component tests ---


@pytest.mark.django_db(transaction=True)
class TestAdAnnounceComponent:
    @pytest.fixture()
    def mock_bot(self):
        bot = MagicMock()
        bot.bot_id = "66977097"
        bot._channel_map = {
            "testchannel": {
                "name": "testchannel",
                "twitch_channel_id": "99999",
            }
        }
        mock_broadcaster = AsyncMock()
        bot.create_partialuser.return_value = mock_broadcaster
        return bot

    @pytest.fixture()
    def component(self, mock_bot):
        comp = AdAnnounce(mock_bot)
        comp._slug_map = {"testchannel": "99999"}
        return comp

    @pytest.fixture()
    def skill(self, make_skill):
        return make_skill(name="ads", config={})

    def _make_event(self, event_type, data=None):
        return json.dumps({
            "event_type": event_type,
            "source": "ads",
            "timestamp": "2026-03-05T22:45:00+00:00",
            "data": data or {},
        }).encode()

    async def test_handle_running_event(self, component, skill, mock_bot):
        raw = self._make_event("ads:running", {"duration": 90})
        await component._handle_event(b"events:testchannel:ads", raw)

        mock_bot.create_partialuser.assert_called_once_with(id="99999")
        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert "90" in msg
        assert "interruption" in msg

    async def test_handle_ended_event(self, component, skill, mock_bot):
        raw = self._make_event("ads:ended")
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert "irregularly scheduled" in msg

    async def test_handle_enabled_event(self, component, skill, mock_bot):
        raw = self._make_event("ads:enabled", {"next_time": "2026-03-05T23:00:00+00:00"})
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert "enabled" in msg.lower()

    async def test_handle_disabled_event(self, component, skill, mock_bot):
        raw = self._make_event("ads:disabled")
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert "disabled" in msg.lower()

    async def test_warning_at_60_seconds(self, component, skill, mock_bot):
        raw = self._make_event("ads:warning", {"seconds": 60})
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert "60" in msg
        assert "emergency" in msg.lower()

    async def test_warning_at_5_seconds(self, component, skill, mock_bot):
        raw = self._make_event("ads:warning", {"seconds": 5})
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert "5" in msg

    async def test_warning_ignored_at_30_seconds(self, component, skill, mock_bot):
        """Default intervals are [60, 5], so 30s should be ignored."""
        raw = self._make_event("ads:warning", {"seconds": 30})
        await component._handle_event(b"events:testchannel:ads", raw)

        mock_bot.create_partialuser.return_value.send_message.assert_not_called()

    async def test_warning_tolerance(self, component, skill, mock_bot):
        """Warning at 62s should still match the 60s interval (within ±5s)."""
        raw = self._make_event("ads:warning", {"seconds": 62})
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        broadcaster.send_message.assert_called_once()

    async def test_warning_outside_tolerance(self, component, skill, mock_bot):
        """Warning at 50s should not match any default interval."""
        raw = self._make_event("ads:warning", {"seconds": 50})
        await component._handle_event(b"events:testchannel:ads", raw)

        mock_bot.create_partialuser.return_value.send_message.assert_not_called()

    async def test_custom_warning_intervals(self, component, mock_bot, make_skill):
        make_skill(name="ads", config={"warning_intervals": [30, 10]})
        raw = self._make_event("ads:warning", {"seconds": 30})
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        broadcaster.send_message.assert_called_once()

    async def test_custom_messages(self, component, mock_bot, make_skill):
        make_skill(
            name="ads",
            config={"messages": {"running": "Ads for $(duration)s, brb!"}},
        )
        raw = self._make_event("ads:running", {"duration": 120})
        await component._handle_event(b"events:testchannel:ads", raw)

        broadcaster = mock_bot.create_partialuser.return_value
        msg = broadcaster.send_message.call_args.kwargs["message"]
        assert msg == "Ads for 120s, brb!"

    async def test_unknown_slug_ignored(self, component, skill, mock_bot):
        raw = self._make_event("ads:running", {"duration": 90})
        await component._handle_event(b"events:unknownchannel:ads", raw)

        mock_bot.create_partialuser.assert_not_called()

    async def test_skill_disabled_ignored(self, component, mock_bot, make_skill):
        make_skill(name="ads", enabled=False)
        raw = self._make_event("ads:running", {"duration": 90})
        await component._handle_event(b"events:testchannel:ads", raw)

        mock_bot.create_partialuser.assert_not_called()

    async def test_no_skill_ignored(self, component, mock_bot):
        """No ads skill record at all — should silently skip."""
        raw = self._make_event("ads:running", {"duration": 90})
        await component._handle_event(b"events:testchannel:ads", raw)

        mock_bot.create_partialuser.assert_not_called()

    async def test_unknown_event_type_ignored(self, component, skill, mock_bot):
        raw = self._make_event("ads:unknown_event")
        await component._handle_event(b"events:testchannel:ads", raw)

        mock_bot.create_partialuser.return_value.send_message.assert_not_called()
