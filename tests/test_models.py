from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.models import F


@pytest.mark.django_db
class TestCounterModel:
    def test_create_counter(self, make_counter):
        counter = make_counter(name="death", value=0, label="Death Count")
        assert counter.name == "death"
        assert counter.value == 0
        assert counter.label == "Death Count"

    def test_str_with_label(self, make_counter):
        counter = make_counter(name="death", value=5, label="Death Count")
        assert "Death Count: 5" in str(counter)

    def test_str_without_label(self, make_counter):
        counter = make_counter(name="death", value=5, label="")
        assert "Death: 5" in str(counter)

    def test_unique_together(self, make_counter, channel):
        make_counter(name="death")
        with pytest.raises(IntegrityError):
            from core.models import Counter

            Counter.objects.create(channel=channel, name="death")

    def test_atomic_increment_with_f_expression(self, make_counter):
        from core.models import Counter

        counter = make_counter(name="death", value=10)

        Counter.objects.filter(pk=counter.pk).update(value=F("value") + 1)
        counter.refresh_from_db()
        assert counter.value == 11

    def test_atomic_decrement_with_f_expression(self, make_counter):
        from core.models import Counter

        counter = make_counter(name="death", value=10)

        Counter.objects.filter(pk=counter.pk).update(value=F("value") - 1)
        counter.refresh_from_db()
        assert counter.value == 9

    def test_default_ordering(self, make_counter):
        from core.models import Counter

        make_counter(name="zebra")
        make_counter(name="alpha")
        make_counter(name="middle")

        names = list(
            Counter.objects.values_list("name", flat=True)
        )
        assert names == ["alpha", "middle", "zebra"]


@pytest.mark.django_db
class TestAliasModel:
    def test_create_alias(self, make_alias):
        alias = make_alias(name="ct", target="count death")
        assert alias.name == "ct"
        assert alias.target == "count death"

    def test_str(self, make_alias):
        alias = make_alias(name="ct", target="count death")
        result = str(alias)
        assert "!ct" in result
        assert "!count death" in result

    def test_unique_together(self, make_alias, channel):
        make_alias(name="ct", target="count death")
        with pytest.raises(IntegrityError):
            from core.models import Alias

            Alias.objects.create(
                channel=channel, name="ct", target="count scare"
            )

    def test_default_ordering(self, make_alias):
        from core.models import Alias

        make_alias(name="z", target="hello")
        make_alias(name="a", target="world")
        make_alias(name="m", target="test")

        names = list(Alias.objects.values_list("name", flat=True))
        assert names == ["a", "m", "z"]


@pytest.mark.django_db
class TestCommandModel:
    def test_create_command(self, make_command):
        cmd = make_command(name="hello", response="Hi $(user)!")
        assert cmd.name == "hello"
        assert cmd.response == "Hi $(user)!"
        assert cmd.enabled is True
        assert cmd.use_count == 0

    def test_default_type_is_text(self, make_command):
        from core.models import Command

        cmd = make_command(name="hello")
        assert cmd.type == Command.Type.TEXT

    def test_type_choices(self, make_command):
        from core.models import Command

        cmd = make_command(name="flask", type=Command.Type.LOTTERY)
        assert cmd.type == "lottery"

        cmd2 = make_command(name="conch", type=Command.Type.RANDOM_LIST)
        assert cmd2.type == "random_list"

        cmd3 = make_command(name="death", type=Command.Type.COUNTER)
        assert cmd3.type == "counter"

    def test_config_default_is_empty_dict(self, make_command):
        cmd = make_command(name="hello")
        assert cmd.config == {}

    def test_config_stores_json(self, make_command):
        cmd = make_command(
            name="flask",
            type="lottery",
            config={"odds": 5, "success": "Win!", "failure": "Lose!"},
        )
        assert cmd.config["odds"] == 5
        assert cmd.config["success"] == "Win!"

    def test_str(self, make_command):
        cmd = make_command(name="hello")
        assert "!hello" in str(cmd)

    def test_unique_together(self, make_command, channel):
        make_command(name="hello")
        with pytest.raises(IntegrityError):
            from core.models import Command

            Command.objects.create(
                channel=channel, name="hello", response="duplicate"
            )

    def test_use_count_increment(self, make_command):
        cmd = make_command(name="test")
        cmd.use_count += 1
        cmd.save(update_fields=["use_count"])
        cmd.refresh_from_db()
        assert cmd.use_count == 1

    def test_response_blank_allowed(self, make_command):
        cmd = make_command(name="flask", type="lottery", response="")
        assert cmd.response == ""


@pytest.mark.django_db
class TestSkillModel:
    def test_create_skill(self, make_skill):
        skill = make_skill(name="conch", config={"responses": ["Yes"]})
        assert skill.name == "conch"
        assert skill.enabled is True
        assert skill.config == {"responses": ["Yes"]}

    def test_str_enabled(self, make_skill):
        skill = make_skill(name="conch")
        assert "enabled" in str(skill)

    def test_str_disabled(self, make_skill):
        skill = make_skill(name="conch", enabled=False)
        assert "disabled" in str(skill)

    def test_unique_together(self, make_skill, channel):
        make_skill(name="conch")
        with pytest.raises(IntegrityError):
            from core.models import Skill

            Skill.objects.create(channel=channel, name="conch")
