from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bot.skills import SKILL_REGISTRY
from bot.skills import SkillHandler
from bot.skills import discover_skills
from bot.skills.followcheck import FollowCheckHandler
from bot.skills.followcheck import format_timesince
from tests.conftest import MockBroadcaster
from tests.conftest import MockChatter
from tests.conftest import MockPayload

# --- Skill registry tests ---


class TestSkillRegistry:
    def test_discover_skills_runs_without_error(self):
        discover_skills()

    def test_registry_is_dict(self):
        assert isinstance(SKILL_REGISTRY, dict)

    def test_skill_handler_base_class_raises(self):
        handler = SkillHandler()
        assert handler.name == ""

    def test_discover_skills_registers_checkme(self):
        discover_skills()
        assert "checkme" in SKILL_REGISTRY
        assert isinstance(SKILL_REGISTRY["checkme"], FollowCheckHandler)


# --- Command type dispatch tests ---
# These test the router's _resolve_response method via full event_message flow.
# Type-specific behavior tests are in test_router.py alongside text command tests.


@pytest.mark.django_db(transaction=True)
class TestLotteryType:
    async def test_lottery_success_at_100_percent(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter
        from tests.conftest import MockBroadcaster
        from tests.conftest import MockPayload

        make_command(
            name="flask",
            type="lottery",
            response="",
            config={
                "odds": 100,
                "success": "$(user) wins!",
                "failure": "Nope!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "TestUser wins!"

    async def test_lottery_failure_at_0_percent(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="flask",
            type="lottery",
            response="",
            config={
                "odds": 0,
                "success": "Win!",
                "failure": "You can't get ye flask, $(user)!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "You can't get ye flask, TestUser!"

    async def test_lottery_increments_use_count(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        cmd = make_command(
            name="flask",
            type="lottery",
            config={"odds": 100, "success": "Win!", "failure": "Lose!"},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        cmd.refresh_from_db()
        assert cmd.use_count == 1


@pytest.mark.django_db(transaction=True)
class TestCommandCooldown:
    async def test_user_cooldown_blocks_second_attempt(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="flask",
            type="lottery",
            user_cooldown_seconds=300,
            config={
                "odds": 100,
                "success": "Win!",
                "failure": "Lose!",
                "cooldown_response": "$(user), wait!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload1 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload1)
        payload1.respond.assert_called_once()
        assert payload1.respond.call_args[0][0] == "Win!"

        # Second attempt — should get cooldown response
        payload2 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload2)
        payload2.respond.assert_called_once()
        assert payload2.respond.call_args[0][0] == "TestUser, wait!"

    async def test_cooldown_does_not_increment_use_count(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        cmd = make_command(
            name="flask",
            type="lottery",
            user_cooldown_seconds=300,
            config={
                "odds": 100,
                "success": "Win!",
                "failure": "Lose!",
                "cooldown_response": "Wait!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        # First use — increments
        payload1 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload1)
        cmd.refresh_from_db()
        assert cmd.use_count == 1

        # Second use — cooldown, no increment
        payload2 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload2)
        cmd.refresh_from_db()
        assert cmd.use_count == 1

    async def test_cooldown_silent_when_no_response_configured(
        self, make_command
    ):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="flask",
            type="lottery",
            user_cooldown_seconds=300,
            config={
                "odds": 100,
                "success": "Win!",
                "failure": "Lose!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload1 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload1)
        payload1.respond.assert_called_once()

        # Second attempt — no cooldown_response, so silent
        payload2 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload2)
        payload2.respond.assert_not_called()

    async def test_different_users_have_separate_cooldowns(
        self, make_command
    ):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="flask",
            type="lottery",
            user_cooldown_seconds=300,
            config={
                "odds": 100,
                "success": "$(user) wins!",
                "failure": "Lose!",
                "cooldown_response": "Wait!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        # User A
        payload_a = MockPayload(
            text="!flask",
            chatter=MockChatter(name="usera", display_name="UserA", id=111),
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload_a)
        payload_a.respond.assert_called_once()
        assert payload_a.respond.call_args[0][0] == "UserA wins!"

        # User B — different user, no cooldown
        payload_b = MockPayload(
            text="!flask",
            chatter=MockChatter(name="userb", display_name="UserB", id=222),
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload_b)
        payload_b.respond.assert_called_once()
        assert payload_b.respond.call_args[0][0] == "UserB wins!"

    async def test_no_cooldown_when_zero(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="flask",
            type="lottery",
            config={
                "odds": 100,
                "success": "Win!",
                "failure": "Lose!",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload1 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload1)
        payload1.respond.assert_called_once()

        # No cooldown — second attempt works normally
        payload2 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload2)
        payload2.respond.assert_called_once()

    async def test_remaining_time_in_cooldown_response(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="flask",
            type="lottery",
            user_cooldown_seconds=3600,
            config={
                "odds": 100,
                "success": "Win!",
                "failure": "Lose!",
                "cooldown_response": "$(user), you have $(remaining) seconds left.",
            },
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload1 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload1)
        payload1.respond.assert_called_once()

        # Second attempt — should include remaining seconds
        payload2 = MockPayload(
            text="!flask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload2)
        payload2.respond.assert_called_once()
        response = payload2.respond.call_args[0][0]
        # Should contain user name and raw seconds (close to 3600)
        assert response.startswith("TestUser, you have ")
        assert response.endswith(" seconds left.")
        # Extract the number and verify it's close to 3600
        seconds = int(response.split("you have ")[1].split(" seconds")[0])
        assert 3590 <= seconds <= 3600

    async def test_global_cooldown_blocks_all_users(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="shout",
            type="text",
            response="Hello!",
            cooldown_seconds=60,
            config={"cooldown_response": "Command on cooldown!"},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        # User A triggers it
        payload_a = MockPayload(
            text="!shout",
            chatter=MockChatter(name="usera", display_name="UserA", id=111),
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload_a)
        payload_a.respond.assert_called_once()
        assert payload_a.respond.call_args[0][0] == "Hello!"

        # User B — blocked by global cooldown
        payload_b = MockPayload(
            text="!shout",
            chatter=MockChatter(name="userb", display_name="UserB", id=222),
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload_b)
        payload_b.respond.assert_called_once()
        assert payload_b.respond.call_args[0][0] == "Command on cooldown!"

    async def test_cooldown_works_on_text_commands(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="greet",
            type="text",
            response="Hi $(user)!",
            user_cooldown_seconds=30,
            config={"cooldown_response": "Slow down!"},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload1 = MockPayload(
            text="!greet",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload1)
        payload1.respond.assert_called_once()
        assert payload1.respond.call_args[0][0] == "Hi TestUser!"

        # Second attempt — cooldown
        payload2 = MockPayload(
            text="!greet",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload2)
        payload2.respond.assert_called_once()
        assert payload2.respond.call_args[0][0] == "Slow down!"


@pytest.mark.django_db(transaction=True)
class TestRandomListType:
    async def test_random_list_picks_from_responses(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        responses = ["Yes.", "No.", "Maybe."]
        make_command(
            name="conch",
            type="random_list",
            config={"responses": responses},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!conch question?",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response in responses

    async def test_random_list_with_prefix(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="conch",
            type="random_list",
            config={"prefix": "\U0001f41a ", "responses": ["Yes."]},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!conch",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "\U0001f41a Yes."

    async def test_random_list_empty_responses_uses_response_field(
        self, make_command
    ):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="conch",
            type="random_list",
            response="No responses configured.",
            config={"responses": []},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!conch",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "No responses configured."

    async def test_random_list_empty_responses_no_fallback(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="conch",
            type="random_list",
            response="",
            config={"responses": []},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!conch",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_random_list_processes_variables(self, make_command):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter

        make_command(
            name="greet",
            type="random_list",
            config={"responses": ["Hello $(user)!"]},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!greet",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "Hello TestUser!"


@pytest.mark.django_db(transaction=True)
class TestCounterType:
    async def test_counter_type_auto_increments(self, make_command, channel):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter
        from core.models import Counter

        Counter.objects.create(channel=channel, name="death", value=5)
        make_command(
            name="deaths",
            type="counter",
            response="$(count.get death) deaths so far.",
            config={"counter_name": "death"},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!deaths",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "6 deaths so far."

        # Verify counter was incremented
        counter = Counter.objects.get(channel=channel, name="death")
        assert counter.value == 6

    async def test_counter_type_creates_counter_if_missing(
        self, make_command, channel
    ):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter
        from core.models import Counter

        make_command(
            name="gotcha",
            type="counter",
            response="$(count.get gotcha) bitches gotcha'd.",
            config={"counter_name": "gotcha"},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!gotcha",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        # Counter should be created and incremented to 1
        counter = Counter.objects.get(channel=channel, name="gotcha")
        assert counter.value == 1

    async def test_counter_type_uses_command_name_as_default(
        self, make_command, channel
    ):
        from unittest.mock import MagicMock

        from bot.router import CommandRouter
        from core.models import Counter

        make_command(
            name="death",
            type="counter",
            response="$(count.get death)",
            config={},
        )

        bot = MagicMock()
        bot.bot_id = "00000"
        router = CommandRouter(bot)

        payload = MockPayload(
            text="!death",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        counter = Counter.objects.get(channel=channel, name="death")
        assert counter.value == 1


# --- format_timesince tests ---


class TestFormatTimesince:
    def test_seconds(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(seconds=30)) == "30 seconds"

    def test_one_second(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(seconds=1)) == "1 second"

    def test_minutes(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(minutes=45)) == "45 minutes"

    def test_one_minute(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(minutes=1)) == "1 minute"

    def test_hours(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(hours=5)) == "5 hours"

    def test_one_hour(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(hours=1)) == "1 hour"

    def test_days(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(days=15)) == "15 days"

    def test_one_day(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(days=1)) == "1 day"

    def test_months(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(days=90)) == "3 months"

    def test_one_month(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(days=30)) == "1 month"

    def test_years_and_months(self):
        now = datetime.now(UTC)
        assert (
            format_timesince(now - timedelta(days=450))
            == "1 year, 3 months"
        )

    def test_exact_year(self):
        now = datetime.now(UTC)
        assert format_timesince(now - timedelta(days=365)) == "1 year"

    def test_multiple_years(self):
        now = datetime.now(UTC)
        result = format_timesince(now - timedelta(days=730))
        assert result.startswith("2 years")


# --- FollowCheckHandler tests ---


def _mock_twitch_response(status_code=200, json_data=None):
    """Create a mock httpx-like response for twitch_request."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    return response


@pytest.mark.django_db(transaction=True)
class TestFollowCheckHandler:
    async def test_following_user_gets_timesince(self, channel):
        channel.owner_access_token = "fake_token"
        channel.save()

        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=True
        )

        followed_at = (
            datetime.now(UTC) - timedelta(days=90)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        api_response = _mock_twitch_response(
            json_data={
                "total": 1,
                "data": [
                    {
                        "user_id": "12345",
                        "user_login": "testuser",
                        "user_name": "TestUser",
                        "followed_at": followed_at,
                    }
                ],
            }
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        payload = MockPayload(
            text="!checkme",
            broadcaster=MockBroadcaster(id=99999),
        )

        with patch("bot.skills.followcheck.twitch_request", new_callable=AsyncMock, return_value=api_response):
            await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response.startswith("@TestUser, you have been following for ")
        assert response.endswith("!")
        assert "3 months" in response

    async def test_not_following_user(self, channel):
        channel.owner_access_token = "fake_token"
        channel.save()

        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=True
        )

        api_response = _mock_twitch_response(
            json_data={"total": 0, "data": []}
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        payload = MockPayload(
            text="!checkme",
            broadcaster=MockBroadcaster(id=99999),
        )

        with patch("bot.skills.followcheck.twitch_request", new_callable=AsyncMock, return_value=api_response):
            await router.event_message(payload)

        payload.respond.assert_called_once()
        assert (
            payload.respond.call_args[0][0]
            == "@TestUser, you are not following this channel."
        )

    async def test_broadcaster_gets_broadcaster_message(self, channel):
        channel.owner_access_token = "fake_token"
        channel.save()

        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=True
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        # Chatter ID matches broadcaster ID
        payload = MockPayload(
            text="!checkme",
            chatter=MockChatter(
                name="testchannel",
                display_name="TestChannel",
                id=99999,
            ),
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        assert (
            payload.respond.call_args[0][0]
            == "@TestChannel, you are the broadcaster!"
        )

    async def test_no_owner_token(self, channel):
        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=True
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        payload = MockPayload(
            text="!checkme",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        assert (
            payload.respond.call_args[0][0]
            == "@TestUser, follow check is not available right now."
        )

    async def test_expired_token_refresh_fails_shows_not_available(
        self, channel
    ):
        channel.owner_access_token = "expired_token"
        channel.save()

        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=True
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        payload = MockPayload(
            text="!checkme",
            broadcaster=MockBroadcaster(id=99999),
        )

        # twitch_request returns None when refresh also fails
        with patch("bot.skills.followcheck.twitch_request", new_callable=AsyncMock, return_value=None):
            await router.event_message(payload)

        payload.respond.assert_called_once()
        assert (
            payload.respond.call_args[0][0]
            == "@TestUser, follow check is not available right now."
        )

    async def test_skill_not_enabled_skips(self, channel):
        channel.owner_access_token = "fake_token"
        channel.save()

        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=False
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        payload = MockPayload(
            text="!checkme",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_api_called_with_correct_url_and_params(self, channel):
        channel.owner_access_token = "test_bearer_token"
        channel.save()

        from core.models import Skill

        Skill.objects.create(
            channel=channel, name="checkme", enabled=True
        )

        followed_at = datetime.now(UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        api_response = _mock_twitch_response(
            json_data={
                "total": 1,
                "data": [
                    {
                        "user_id": "12345",
                        "user_login": "testuser",
                        "user_name": "TestUser",
                        "followed_at": followed_at,
                    }
                ],
            }
        )

        bot = MagicMock()
        bot.bot_id = "00000"

        from bot.router import CommandRouter

        router = CommandRouter(bot)

        payload = MockPayload(
            text="!checkme",
            broadcaster=MockBroadcaster(id=99999),
        )

        mock_twitch_request = AsyncMock(return_value=api_response)
        with patch("bot.skills.followcheck.twitch_request", mock_twitch_request):
            await router.event_message(payload)

        mock_twitch_request.assert_called_once()
        call_args = mock_twitch_request.call_args
        # First positional arg is the channel object
        assert call_args[0][1] == "GET"
        assert "channels/followers" in call_args[0][2]
        assert call_args[1]["params"]["broadcaster_id"] == "99999"
        assert call_args[1]["params"]["user_id"] == "12345"
