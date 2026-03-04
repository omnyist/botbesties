from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.management.commands.prunedeepbot import KNOWN_BOTS
from core.management.commands.prunedeepbot import format_user
from core.management.commands.prunedeepbot import parse_iso_datetime


class TestParseIsoDatetime:
    def test_valid_iso(self):
        result = parse_iso_datetime("2024-01-15T10:30:00")
        assert result is not None
        assert result.year == 2024

    def test_valid_iso_with_tz(self):
        result = parse_iso_datetime("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2024

    def test_invalid_string(self):
        assert parse_iso_datetime("not a date") is None

    def test_empty_string(self):
        assert parse_iso_datetime("") is None


class TestFormatUser:
    def test_basic_format(self):
        record = {
            "username": "  KefkaFish  ",
            "displayName": "kefkafish",
            "points": 171661.0,
            "minutes": 12345,
            "firstSeen": "2017-03-07T13:36:15",
            "lastSeen": "2026-02-15T00:00:00",
            "accessLevel": 10,
        }
        result = format_user(record)
        assert result["username"] == "kefkafish"
        assert result["display_name"] == "kefkafish"
        assert result["points"] == 171661.0
        assert result["minutes_watched"] == 12345
        assert result["access_level"] == 10

    def test_missing_display_name(self):
        record = {
            "username": "testuser",
            "points": 0,
            "minutes": 0,
            "firstSeen": "",
            "lastSeen": "",
            "accessLevel": 10,
        }
        result = format_user(record)
        assert result["display_name"] is None

    def test_missing_minutes_defaults_to_zero(self):
        record = {
            "username": "testuser",
            "displayName": "testuser",
            "points": 100.0,
            "firstSeen": "",
            "lastSeen": "",
            "accessLevel": 10,
        }
        result = format_user(record)
        assert result["minutes_watched"] == 0


class TestPruneDeepbotCommand:
    @pytest.mark.django_db
    def test_dry_run(self):
        from django.core.management import call_command
        from io import StringIO

        data = [
            {
                "username": "active_user",
                "displayName": "active_user",
                "points": 100.0,
                "minutes": 120,
                "firstSeen": "2024-01-01T00:00:00",
                "lastSeen": "2025-12-01T00:00:00",
                "accessLevel": 10,
            },
            {
                "username": "inactive_user",
                "displayName": "inactive_user",
                "points": 0.0,
                "minutes": 5,
                "firstSeen": "2020-01-01T00:00:00",
                "lastSeen": "2020-06-01T00:00:00",
                "accessLevel": 10,
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()

            out = StringIO()
            call_command(
                "prunedeepbot", f.name, "--dry-run",
                stdout=out,
            )
            output = out.getvalue()
            assert "DRY RUN" in output

    @pytest.mark.django_db
    def test_elevated_users_always_kept(self):
        from io import StringIO

        from django.core.management import call_command

        data = [
            {
                "username": "mod_user",
                "displayName": "Mod User",
                "points": 0.0,
                "minutes": 0,
                "firstSeen": "2020-01-01T00:00:00",
                "lastSeen": "2020-01-02T00:00:00",
                "accessLevel": 3,
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "pruned.json"
                out = StringIO()
                call_command(
                    "prunedeepbot", f.name,
                    "--output", str(output_path),
                    stdout=out,
                )

                result = json.loads(output_path.read_text())
                assert len(result) == 1
                assert result[0]["username"] == "mod_user"

    @pytest.mark.django_db
    def test_points_filter(self):
        from io import StringIO

        from django.core.management import call_command

        data = [
            {
                "username": "rich_user",
                "displayName": "rich_user",
                "points": 500.0,
                "minutes": 100,
                "firstSeen": "2024-01-01T00:00:00",
                "lastSeen": "2025-12-01T00:00:00",
                "accessLevel": 10,
            },
            {
                "username": "poor_user",
                "displayName": "poor_user",
                "points": 5.0,
                "minutes": 1000,
                "firstSeen": "2024-01-01T00:00:00",
                "lastSeen": "2025-12-01T00:00:00",
                "accessLevel": 10,
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "pruned.json"
                excluded_path = Path(tmpdir) / "excluded_users.json"
                out = StringIO()
                call_command(
                    "prunedeepbot", f.name,
                    "--output", str(output_path),
                    "--min-points", "100",
                    stdout=out,
                )

                pruned = json.loads(output_path.read_text())
                assert len(pruned) == 1
                assert pruned[0]["username"] == "rich_user"

                excluded = json.loads(excluded_path.read_text())
                assert len(excluded) == 1
                assert excluded[0]["username"] == "poor_user"

    @pytest.mark.django_db
    def test_known_bots_excluded(self):
        from io import StringIO

        from django.core.management import call_command

        data = [
            {
                "username": "moobot",
                "displayName": "Moobot",
                "points": 99999.0,
                "minutes": 999999,
                "firstSeen": "2020-01-01T00:00:00",
                "lastSeen": "2026-01-01T00:00:00",
                "accessLevel": 10,
            },
            {
                "username": "real_user",
                "displayName": "real_user",
                "points": 200.0,
                "minutes": 500,
                "firstSeen": "2024-01-01T00:00:00",
                "lastSeen": "2025-12-01T00:00:00",
                "accessLevel": 10,
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "pruned.json"
                out = StringIO()
                call_command(
                    "prunedeepbot", f.name,
                    "--output", str(output_path),
                    stdout=out,
                )

                pruned = json.loads(output_path.read_text())
                usernames = [u["username"] for u in pruned]
                assert "moobot" not in usernames
                assert "real_user" in usernames

    def test_known_bots_list_has_common_bots(self):
        assert "moobot" in KNOWN_BOTS
        assert "nightbot" in KNOWN_BOTS
        assert "streamelements" in KNOWN_BOTS

    @pytest.mark.django_db
    def test_corrupted_records_separated(self):
        from io import StringIO

        from django.core.management import call_command

        data = [
            {
                "username": {"nested": "dict"},
                "points": 100.0,
                "accessLevel": 10,
            },
            {
                "username": "valid_user",
                "displayName": "valid_user",
                "points": 500.0,
                "minutes": 200,
                "firstSeen": "2024-01-01T00:00:00",
                "lastSeen": "2025-12-01T00:00:00",
                "accessLevel": 10,
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            f.flush()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "pruned.json"
                corrupted_path = Path(tmpdir) / "corrupted_users.json"
                out = StringIO()
                call_command(
                    "prunedeepbot", f.name,
                    "--output", str(output_path),
                    stdout=out,
                )

                pruned = json.loads(output_path.read_text())
                assert len(pruned) == 1
                assert pruned[0]["username"] == "valid_user"

                assert corrupted_path.exists()
                corrupted = json.loads(corrupted_path.read_text())
                assert len(corrupted) == 1
