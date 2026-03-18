from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core.models import Bot
from core.models import Channel
from core.models import Command
from core.models import TwitchProfile

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture()
def test_bot():
    return Bot.objects.create(
        name="TestBot",
        twitch_user_id="66977097",
        twitch_username="testbot",
    )


@pytest.fixture()
def test_channel(test_bot):
    return Channel.objects.create(
        bot=test_bot,
        twitch_channel_id="99999",
        twitch_channel_name="testchannel",
        is_active=True,
    )


@pytest.fixture()
def user_with_profile(test_channel):
    """Create a Django user with a TwitchProfile matching the test channel."""
    user = User.objects.create_user(username="avalonstar", password="testpass")
    TwitchProfile.objects.create(
        user=user,
        twitch_id="99999",
        twitch_username="avalonstar",
        twitch_display_name="Avalonstar",
        twitch_avatar="https://example.com/avatar.png",
    )
    return user


@pytest.fixture()
def other_user():
    """Create a user who does NOT own the test channel."""
    user = User.objects.create_user(username="otheruser", password="testpass")
    TwitchProfile.objects.create(
        user=user,
        twitch_id="11111",
        twitch_username="otheruser",
        twitch_display_name="OtherUser",
    )
    return user


@pytest.fixture()
def authed_client(user_with_profile):
    """A test client logged in as the channel owner."""
    c = Client(enforce_csrf_checks=False)
    c.login(username="avalonstar", password="testpass")
    return c


@pytest.fixture()
def unauthed_client():
    """A test client with no session."""
    return Client()


@pytest.fixture()
def other_client(other_user):
    """A test client logged in as a user who doesn't own the channel."""
    c = Client(enforce_csrf_checks=False)
    c.login(username="otheruser", password="testpass")
    return c


def _make_cmd(test_channel, name="test", response="Hello!", **kwargs):
    """Helper to create a command in the test channel."""
    defaults = {
        "channel": test_channel,
        "name": name,
        "response": response,
        "enabled": True,
    }
    defaults.update(kwargs)
    return Command.objects.create(**defaults)


class TestMeEndpoint:
    def test_returns_user_info(self, authed_client, test_channel):
        response = authed_client.get("/api/v1/me")
        assert response.status_code == 200
        data = response.json()
        assert data["twitch_id"] == "99999"
        assert data["twitch_display_name"] == "Avalonstar"
        assert len(data["channels"]) == 1
        assert data["channels"][0]["name"] == "testchannel"

    def test_unauthenticated_returns_401(self, unauthed_client):
        response = unauthed_client.get("/api/v1/me")
        assert response.status_code == 401


class TestChannelsEndpoint:
    def test_lists_owned_channels(self, authed_client, test_channel):
        response = authed_client.get("/api/v1/channels/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "testchannel"

    def test_excludes_other_channels(self, other_client, test_channel):
        response = other_client.get("/api/v1/channels/")
        assert response.status_code == 200
        assert response.json() == []

    def test_unauthenticated_returns_401(self, unauthed_client):
        response = unauthed_client.get("/api/v1/channels/")
        assert response.status_code == 401


class TestCommandList:
    def test_lists_all_commands(self, authed_client, test_channel):
        _make_cmd(test_channel, name="lurk", response="/me lurks")
        _make_cmd(test_channel, name="conch", enabled=False)

        response = authed_client.get(
            f"/api/v1/commands/channels/{test_channel.twitch_channel_name}/"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [c["name"] for c in data]
        assert "lurk" in names
        assert "conch" in names

    def test_not_found_for_non_owner(self, other_client, test_channel):
        response = other_client.get(
            f"/api/v1/commands/channels/{test_channel.twitch_channel_name}/"
        )
        assert response.status_code == 404

    def test_unauthenticated_returns_401(self, unauthed_client, test_channel):
        response = unauthed_client.get(
            f"/api/v1/commands/channels/{test_channel.twitch_channel_name}/"
        )
        assert response.status_code == 401


class TestCommandCreate:
    def test_creates_command(self, authed_client, test_channel):
        response = authed_client.post(
            f"/api/v1/commands/channels/{test_channel.twitch_channel_name}/",
            data=json.dumps({"name": "hello", "response": "Hello $(user)!"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "hello"
        assert data["response"] == "Hello $(user)!"
        assert data["created_by"] == "Avalonstar"
        assert Command.objects.filter(
            channel=test_channel, name="hello"
        ).exists()

    def test_create_with_config(self, authed_client, test_channel):
        response = authed_client.post(
            f"/api/v1/commands/channels/{test_channel.twitch_channel_name}/",
            data=json.dumps({
                "name": "flask",
                "type": "lottery",
                "config": {
                    "odds": 25,
                    "success": "You win!",
                    "failure": "Nope.",
                },
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "lottery"
        assert data["config"]["odds"] == 25

    def test_not_found_for_non_owner(self, other_client, test_channel):
        response = other_client.post(
            f"/api/v1/commands/channels/{test_channel.twitch_channel_name}/",
            data=json.dumps({"name": "nope"}),
            content_type="application/json",
        )
        assert response.status_code == 404


class TestCommandGet:
    def test_get_single_command(self, authed_client, test_channel):
        cmd = _make_cmd(test_channel, name="lurk", response="/me lurks")
        response = authed_client.get(f"/api/v1/commands/{cmd.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "lurk"

    def test_forbidden_for_non_owner(self, other_client, test_channel):
        cmd = _make_cmd(test_channel, name="lurk")
        response = other_client.get(f"/api/v1/commands/{cmd.id}/")
        assert response.status_code == 403


class TestCommandUpdate:
    def test_updates_response(self, authed_client, test_channel):
        cmd = _make_cmd(test_channel, name="lurk", response="old response")
        response = authed_client.patch(
            f"/api/v1/commands/{cmd.id}/",
            data=json.dumps({"response": "new response"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        cmd.refresh_from_db()
        assert cmd.response == "new response"

    def test_updates_multiple_fields(self, authed_client, test_channel):
        cmd = _make_cmd(test_channel, name="lurk")
        response = authed_client.patch(
            f"/api/v1/commands/{cmd.id}/",
            data=json.dumps({
                "enabled": False,
                "mod_only": True,
                "cooldown_seconds": 30,
            }),
            content_type="application/json",
        )
        assert response.status_code == 200
        cmd.refresh_from_db()
        assert cmd.enabled is False
        assert cmd.mod_only is True
        assert cmd.cooldown_seconds == 30

    def test_forbidden_for_non_owner(self, other_client, test_channel):
        cmd = _make_cmd(test_channel, name="lurk")
        response = other_client.patch(
            f"/api/v1/commands/{cmd.id}/",
            data=json.dumps({"response": "hacked"}),
            content_type="application/json",
        )
        assert response.status_code == 403
        cmd.refresh_from_db()
        assert cmd.response != "hacked"


class TestCommandDelete:
    def test_deletes_command(self, authed_client, test_channel):
        cmd = _make_cmd(test_channel, name="bye")
        response = authed_client.delete(f"/api/v1/commands/{cmd.id}/")
        assert response.status_code == 200
        assert not Command.objects.filter(pk=cmd.id).exists()

    def test_forbidden_for_non_owner(self, other_client, test_channel):
        cmd = _make_cmd(test_channel, name="safe")
        response = other_client.delete(f"/api/v1/commands/{cmd.id}/")
        assert response.status_code == 403
        assert Command.objects.filter(pk=cmd.id).exists()


class TestVariableSchema:
    def test_returns_schema(self, authed_client):
        response = authed_client.get("/api/v1/variables/schema/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        namespaces = [v["namespace"] for v in data]
        assert "user" in namespaces

    def test_unauthenticated_returns_401(self, unauthed_client):
        response = unauthed_client.get("/api/v1/variables/schema/")
        assert response.status_code == 401
