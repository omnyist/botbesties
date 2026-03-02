from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.management.commands.importmoobot import convert_variables
from core.management.commands.importmoobot import has_unsupported_variables
from core.management.commands.importmoobot import uses_counter


# ---------------------------------------------------------------------------
# Helper: build a minimal Moobot export JSON structure
# ---------------------------------------------------------------------------


def _moobot_export(*commands):
    """Build a Moobot export dict with the given command entries."""
    return {
        "version": 1,
        "type": "settings",
        "settings": [
            {
                "type": "commands_custom",
                "data": list(commands),
            }
        ],
    }


def _moobot_cmd(
    identifier,
    text,
    enabled=True,
    counter=0,
    mod_editable=False,
    chat_text=None,
):
    """Build a single Moobot command entry with sensible defaults."""
    cmd = {
        "identifier": identifier,
        "text": text,
        "enabled": enabled,
        "counter": counter,
        "counter_trigger_increment": True,
        "cooldown": 5,
        "mod_editable": mod_editable,
        "trigger_usergroups": [0, 1, 2, 3, 4],
    }
    if chat_text is not None:
        cmd["chat_text"] = chat_text
    return cmd


def _write_export(data):
    """Write export data to a temp JSON file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, f)
    f.close()
    return f.name


# ===========================================================================
# Unit tests for helper functions
# ===========================================================================


class TestConvertVariables:
    """Test Moobot → Botbesties variable conversion."""

    def test_username(self):
        assert convert_variables("Hello <username>!") == "Hello $(user)!"

    def test_args(self):
        assert convert_variables("<username> hugs <args>") == "$(user) hugs $(target)"

    def test_twitch_game(self):
        assert convert_variables("Playing <twitch.game>") == "Playing $(game)"

    def test_twitch_uptime(self):
        assert convert_variables("Up for <twitch.uptime>") == "Up for $(uptime)"

    def test_no_variables(self):
        assert convert_variables("Just text") == "Just text"

    def test_multiple_same_variable(self):
        result = convert_variables("<username> and <username>")
        assert result == "$(user) and $(user)"


class TestHasUnsupportedVariables:
    """Test detection of unsupported Moobot variables."""

    def test_time_unsupported(self):
        assert "<time>" in has_unsupported_variables("It is <time>.")

    def test_twitch_followed_unsupported(self):
        assert "<twitch.followed>" in has_unsupported_variables("<twitch.followed>")

    def test_supported_variables_not_flagged(self):
        assert has_unsupported_variables("<username> plays <twitch.game>") == []

    def test_plain_text(self):
        assert has_unsupported_variables("Hello world") == []


class TestUsesCounter:
    """Test detection of Moobot <counter> variable."""

    def test_has_counter(self):
        assert uses_counter("Done <counter> times.") is True

    def test_no_counter(self):
        assert uses_counter("Just text") is False


# ===========================================================================
# Integration tests (Django DB)
# ===========================================================================


@pytest.mark.django_db
class TestImportMoobotCommand:
    """Test the importmoobot management command end-to-end."""

    def test_simple_text_command(self, channel):
        data = _moobot_export(
            _moobot_cmd("lurk", "Enjoy your lurk, <username>!")
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        cmd = Command.objects.get(channel=channel, name="lurk")
        assert cmd.response == "Enjoy your lurk, $(user)!"
        assert cmd.enabled is True
        assert cmd.created_by == "testchannel"

    def test_disabled_command(self, channel):
        data = _moobot_export(
            _moobot_cmd("oldcmd", "Old stuff", enabled=False)
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        cmd = Command.objects.get(channel=channel, name="oldcmd")
        assert cmd.enabled is False

    def test_counter_command_creates_counter(self, channel):
        data = _moobot_export(
            _moobot_cmd("miq", "Gotcha! (<counter> times)", counter=255)
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command
        from core.models import Counter

        cmd = Command.objects.get(channel=channel, name="miq")
        assert "$(count.get miq)" in cmd.response
        assert cmd.use_count == 255

        counter = Counter.objects.get(channel=channel, name="miq")
        assert counter.value == 255
        assert counter.label == "Miq"

    def test_followage_creates_alias(self, channel):
        data = _moobot_export(
            _moobot_cmd("followage", "<twitch.followed>")
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Alias
        from core.models import Command

        alias = Alias.objects.get(channel=channel, name="followage")
        assert alias.target == "followage"
        assert not Command.objects.filter(channel=channel, name="followage").exists()

    def test_unsupported_variable_skipped(self, channel):
        data = _moobot_export(
            _moobot_cmd("localtime", "The time is <time>.")
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        assert not Command.objects.filter(channel=channel, name="localtime").exists()

    def test_mod_editable_uses_chat_text(self, channel):
        data = _moobot_export(
            _moobot_cmd(
                "archive",
                "<text>",
                mod_editable=True,
                chat_text="Watch old streams here!",
            )
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        cmd = Command.objects.get(channel=channel, name="archive")
        assert cmd.response == "Watch old streams here!"

    def test_existing_command_skipped(self, channel, make_command):
        make_command(name="lurk", response="Already here!")

        data = _moobot_export(
            _moobot_cmd("lurk", "Moobot version")
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        cmd = Command.objects.get(channel=channel, name="lurk")
        assert cmd.response == "Already here!"

    def test_dry_run_creates_nothing(self, channel):
        data = _moobot_export(
            _moobot_cmd("lurk", "Enjoy your lurk!"),
            _moobot_cmd("miq", "Gotcha (<counter>)", counter=10),
            _moobot_cmd("followage", "<twitch.followed>"),
        )
        path = _write_export(data)

        call_command(
            "importmoobot", path, channel="testchannel", dry_run=True
        )

        from core.models import Alias
        from core.models import Command
        from core.models import Counter

        assert Command.objects.filter(channel=channel).count() == 0
        assert Counter.objects.filter(channel=channel).count() == 0
        assert Alias.objects.filter(channel=channel).count() == 0

    def test_preserves_use_count(self, channel):
        data = _moobot_export(
            _moobot_cmd("discord", "Join discord!", counter=124)
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        cmd = Command.objects.get(channel=channel, name="discord")
        assert cmd.use_count == 124

    def test_multiple_commands(self, channel):
        data = _moobot_export(
            _moobot_cmd("lurk", "Enjoy lurk, <username>!"),
            _moobot_cmd("discord", "Join us!"),
            _moobot_cmd("salt", "Salt: <counter>", counter=6),
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command
        from core.models import Counter

        assert Command.objects.filter(channel=channel).count() == 3
        assert Counter.objects.filter(channel=channel, name="salt").exists()

    def test_file_not_found(self, channel):
        with pytest.raises(CommandError, match="File not found"):
            call_command(
                "importmoobot", "/nonexistent.json", channel="testchannel"
            )

    def test_channel_not_found(self, channel):
        data = _moobot_export(_moobot_cmd("lurk", "hi"))
        path = _write_export(data)

        with pytest.raises(CommandError, match="Channel not found"):
            call_command("importmoobot", path, channel="nosuch")

    def test_no_commands_custom_section(self, channel):
        data = {"version": 1, "type": "settings", "settings": []}
        path = _write_export(data)

        with pytest.raises(CommandError, match="commands_custom"):
            call_command("importmoobot", path, channel="testchannel")

    def test_twitch_game_variable_converted(self, channel):
        data = _moobot_export(
            _moobot_cmd("silentmode", "Enjoy <twitch.game>.")
        )
        path = _write_export(data)

        call_command("importmoobot", path, channel="testchannel")

        from core.models import Command

        cmd = Command.objects.get(channel=channel, name="silentmode")
        assert cmd.response == "Enjoy $(game)."
