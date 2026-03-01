from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from dataclasses import field
from unittest.mock import AsyncMock

import pytest

# Allow sync ORM calls from async test functions.
# This is standard practice for Django async testing — fixtures create
# data synchronously while test bodies use sync_to_async for handler calls.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


# --- Mock TwitchIO objects ---
# We mock these instead of importing from twitchio because
# the real classes require websocket connections and parsed IRC data.


@dataclass
class MockChatter:
    """Mocks twitchio.Chatter for tests."""

    name: str = "testuser"
    display_name: str = "TestUser"
    id: int = 12345
    moderator: bool = False
    broadcaster: bool = False


@dataclass
class MockBroadcaster:
    """Mocks the broadcaster object on ChatMessage."""

    name: str = "testchannel"
    display_name: str = "TestChannel"
    id: int = 99999


@dataclass
class MockPayload:
    """Mocks twitchio.ChatMessage for tests."""

    text: str = ""
    chatter: MockChatter = field(default_factory=MockChatter)
    broadcaster: MockBroadcaster = field(default_factory=MockBroadcaster)
    respond: AsyncMock = field(default_factory=AsyncMock)


@pytest.fixture()
def mock_chatter():
    """Create a default non-privileged chatter."""
    return MockChatter()


@pytest.fixture()
def mock_mod_chatter():
    """Create a moderator chatter."""
    return MockChatter(name="moduser", display_name="ModUser", id=11111, moderator=True)


@pytest.fixture()
def mock_broadcaster_chatter():
    """Create a broadcaster chatter."""
    return MockChatter(name="broadcastuser", display_name="BroadcastUser", id=22222, broadcaster=True)


@pytest.fixture()
def mock_broadcaster():
    """Create a default broadcaster (channel owner)."""
    return MockBroadcaster()


@pytest.fixture()
def make_payload():
    """Factory fixture for creating mock payloads."""

    def _make(
        text="",
        chatter=None,
        broadcaster=None,
    ):
        return MockPayload(
            text=text,
            chatter=chatter or MockChatter(),
            broadcaster=broadcaster or MockBroadcaster(),
        )

    return _make


# --- Django model fixtures ---


@pytest.fixture()
def bot(db):
    """Create a Bot instance."""
    from core.models import Bot

    return Bot.objects.create(
        name="TestBot",
        twitch_user_id="66977097",
        twitch_username="testbot",
    )


@pytest.fixture()
def channel(bot):
    """Create a Channel instance linked to the bot."""
    from core.models import Channel

    return Channel.objects.create(
        bot=bot,
        twitch_channel_id="99999",
        twitch_channel_name="testchannel",
        is_active=True,
    )


@pytest.fixture()
def make_command(channel):
    """Factory fixture for creating Command instances."""

    def _make(name="test", response="Hello $(user)!", **kwargs):
        from core.models import Command

        defaults = {
            "channel": channel,
            "name": name,
            "response": response,
            "enabled": True,
        }
        defaults.update(kwargs)
        return Command.objects.create(**defaults)

    return _make


@pytest.fixture()
def make_counter(channel):
    """Factory fixture for creating Counter instances."""

    def _make(name="death", value=0, label="", **kwargs):
        from core.models import Counter

        defaults = {
            "channel": channel,
            "name": name,
            "value": value,
            "label": label,
        }
        defaults.update(kwargs)
        return Counter.objects.create(**defaults)

    return _make


@pytest.fixture()
def make_alias(channel):
    """Factory fixture for creating Alias instances."""

    def _make(name="ct", target="count death", **kwargs):
        from core.models import Alias

        defaults = {
            "channel": channel,
            "name": name,
            "target": target,
        }
        defaults.update(kwargs)
        return Alias.objects.create(**defaults)

    return _make


@pytest.fixture()
def make_skill(channel):
    """Factory fixture for creating Skill instances."""

    def _make(name="conch", enabled=True, config=None, **kwargs):
        from core.models import Skill

        defaults = {
            "channel": channel,
            "name": name,
            "enabled": enabled,
            "config": config or {},
        }
        defaults.update(kwargs)
        return Skill.objects.create(**defaults)

    return _make


@pytest.fixture()
def variable_context():
    """Create a default VariableContext for testing."""
    from bot.variables import VariableContext

    return VariableContext(
        user="TestUser",
        target="TargetUser",
        channel_name="testchannel",
        broadcaster_id="99999",
        command_name="test",
        use_count=42,
        raw_args="arg1 arg2 arg3",
    )


@pytest.fixture()
def registry():
    """Create a populated VariableRegistry."""
    from bot.variables import create_registry

    return create_registry()
