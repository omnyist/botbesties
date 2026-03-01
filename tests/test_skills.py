from __future__ import annotations

from unittest.mock import patch

import pytest

from bot.skills import SKILL_REGISTRY
from bot.skills import SkillHandler
from bot.skills import discover_skills
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


# --- Command type dispatch tests ---
# These test the router's _resolve_response method via full event_message flow.
# Type-specific behavior tests are in test_router.py alongside text command tests.


@pytest.mark.django_db(transaction=True)
class TestLotteryType:
    async def test_lottery_success_at_100_percent(self, make_command):
        from bot.router import CommandRouter
        from tests.conftest import MockBroadcaster
        from tests.conftest import MockPayload
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from core.models import Command
        from unittest.mock import MagicMock

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
class TestRandomListType:
    async def test_random_list_picks_from_responses(self, make_command):
        from bot.router import CommandRouter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from core.models import Counter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from core.models import Counter
        from unittest.mock import MagicMock

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
        from bot.router import CommandRouter
        from core.models import Counter
        from unittest.mock import MagicMock

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
