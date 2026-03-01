from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest

from bot.router import BUILTIN_COMMANDS
from bot.router import CommandRouter
from tests.conftest import MockBroadcaster
from tests.conftest import MockChatter
from tests.conftest import MockPayload


# --- Helpers ---


def _make_bot(bot_id="00000"):
    """Create a minimal mock bot for the CommandRouter."""
    bot = MagicMock()
    bot.bot_id = bot_id
    return bot


def _make_router(bot_id="00000"):
    """Create a CommandRouter with a mock bot."""
    bot = _make_bot(bot_id=bot_id)
    return CommandRouter(bot)


# --- Tests ---


class TestBuiltinCommands:
    """Verify all management commands are in the skip list."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "addcom",
            "editcom",
            "delcom",
            "commands",
            "id",
            "alias",
            "unalias",
            "aliases",
            "count",
            "counters",
        ],
    )
    def test_builtin_commands_in_set(self, cmd):
        assert cmd in BUILTIN_COMMANDS


@pytest.mark.django_db(transaction=True)
class TestCommandRouterTextCommands:
    """Test the text command path."""

    async def test_responds_to_text_command(self, make_command):
        make_command(name="hello", response="Hello $(user)!")
        router = _make_router()

        payload = MockPayload(
            text="!hello",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "Hello testuser!"

    async def test_increments_use_count(self, make_command):
        from core.models import Command

        cmd = make_command(name="ping", response="pong")
        assert cmd.use_count == 0

        router = _make_router()
        payload = MockPayload(
            text="!ping",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        cmd.refresh_from_db()
        assert cmd.use_count == 1

    async def test_ignores_disabled_command(self, make_command):
        make_command(name="disabled", response="should not see this", enabled=False)
        router = _make_router()

        payload = MockPayload(
            text="!disabled",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_ignores_unknown_command(self, channel):
        router = _make_router()

        payload = MockPayload(
            text="!nonexistent",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_me_action_message(self, make_command):
        make_command(name="lurk", response="/me $(user) lurks.")
        router = _make_router()

        payload = MockPayload(
            text="!lurk",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once_with("testuser lurks.", me=True)

    async def test_me_action_with_dash_separator(self, make_command):
        make_command(
            name="lurk",
            response="/me - $(user) settles in for a cozy lurk.",
        )
        router = _make_router()

        payload = MockPayload(
            text="!lurk",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        response = payload.respond.call_args[0][0]
        kwargs = payload.respond.call_args[1]
        assert kwargs["me"] is True
        assert response == "testuser settles in for a cozy lurk."

    async def test_target_variable_from_args(self, make_command):
        make_command(name="hug", response="$(user) hugs $(target)!")
        router = _make_router()

        payload = MockPayload(
            text="!hug @Bryan",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once_with("testuser hugs Bryan!", me=False)

    async def test_target_falls_back_to_user(self, make_command):
        make_command(name="hug", response="$(user) hugs $(target)!")
        router = _make_router()

        payload = MockPayload(
            text="!hug",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once_with(
            "testuser hugs testuser!", me=False
        )


@pytest.mark.django_db(transaction=True)
class TestCommandRouterGuards:
    """Test message filtering and guard logic."""

    async def test_ignores_self_messages(self, channel):
        router = _make_router(bot_id="12345")

        payload = MockPayload(
            text="!hello",
            chatter=MockChatter(id=12345),
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_ignores_non_command_messages(self, channel):
        router = _make_router()

        payload = MockPayload(
            text="just chatting",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_ignores_builtin_commands(self, channel):
        router = _make_router()

        payload = MockPayload(
            text="!addcom test hello",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_ignores_count_builtin(self, channel):
        """!count is a builtin management command, not routed."""
        router = _make_router()

        payload = MockPayload(
            text="!count death +",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_ignores_empty_command(self, channel):
        router = _make_router()

        payload = MockPayload(
            text="!",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()

    async def test_command_name_is_case_insensitive(self, make_command):
        make_command(name="hello", response="Hi!")
        router = _make_router()

        payload = MockPayload(
            text="!HELLO",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once_with("Hi!", me=False)


@pytest.mark.django_db(transaction=True)
class TestCommandRouterAliases:
    """Test alias resolution in the router."""

    async def test_alias_resolves_to_text_command(
        self, make_command, make_alias
    ):
        make_command(name="hello", response="Hi from $(user)!")
        make_alias(name="hi", target="hello")
        router = _make_router()

        payload = MockPayload(
            text="!hi",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "Hi from testuser!"

    async def test_alias_resolves_to_typed_command(
        self, make_command, make_alias
    ):
        """Aliases work for all command types, not just text."""
        make_command(
            name="conch",
            type="random_list",
            config={"responses": ["Yes."]},
        )
        make_alias(name="ask", target="conch")
        router = _make_router()

        payload = MockPayload(
            text="!ask",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_called_once()
        response = payload.respond.call_args[0][0]
        assert response == "Yes."

    async def test_alias_nonexistent_does_nothing(self, channel):
        """An alias pointing to a non-existent command silently does nothing."""
        from core.models import Alias

        Alias.objects.create(
            channel=channel, name="ghost", target="nonexistent"
        )
        router = _make_router()

        payload = MockPayload(
            text="!ghost",
            broadcaster=MockBroadcaster(id=99999),
        )
        await router.event_message(payload)

        payload.respond.assert_not_called()


@pytest.mark.django_db(transaction=True)
class TestCommandRouterSkillFallback:
    """Test skill handler fallback for complex behaviors."""

    async def test_skill_fallback_dispatches(self, make_skill):
        """Skill handlers still work for commands not in the Command table."""
        from bot.skills import SKILL_REGISTRY
        from bot.skills import SkillHandler
        from bot.skills import register_skill

        class TestSkillHandler(SkillHandler):
            name = "testskill"

            async def handle(self, payload, args, skill):
                await payload.respond(f"Skill response: {args}")

        register_skill(TestSkillHandler())

        try:
            make_skill(name="testskill")
            router = _make_router()

            payload = MockPayload(
                text="!testskill hello",
                broadcaster=MockBroadcaster(id=99999),
            )
            await router.event_message(payload)

            payload.respond.assert_called_once_with("Skill response: hello")
        finally:
            SKILL_REGISTRY.pop("testskill", None)

    async def test_command_takes_priority_over_skill(
        self, make_skill, make_command
    ):
        """When a command and skill share a name, command wins."""
        from bot.skills import SKILL_REGISTRY
        from bot.skills import SkillHandler
        from bot.skills import register_skill

        class ConflictHandler(SkillHandler):
            name = "conflictcmd"

            async def handle(self, payload, args, skill):
                await payload.respond("Skill response")

        register_skill(ConflictHandler())

        try:
            make_skill(name="conflictcmd")
            make_command(name="conflictcmd", response="Command response")
            router = _make_router()

            payload = MockPayload(
                text="!conflictcmd",
                broadcaster=MockBroadcaster(id=99999),
            )
            await router.event_message(payload)

            response = payload.respond.call_args[0][0]
            assert response == "Command response"
        finally:
            SKILL_REGISTRY.pop("conflictcmd", None)
