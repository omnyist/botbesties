from __future__ import annotations

from django.db import migrations


SKILL_TYPE_MAP = {
    "conch": "random_list",
    "getyeflask": "lottery",
}


def convert_skills_to_commands(apps, schema_editor):
    """Convert simple Skill records to typed Command records.

    - conch → Command(type="random_list")
    - getyeflask → Command(type="lottery")
    - count → deleted (management command now)
    """
    Skill = apps.get_model("core", "Skill")
    Command = apps.get_model("core", "Command")

    for skill in Skill.objects.filter(name__in=SKILL_TYPE_MAP):
        Command.objects.get_or_create(
            channel=skill.channel,
            name=skill.name,
            defaults={
                "type": SKILL_TYPE_MAP[skill.name],
                "config": skill.config,
                "response": "",
                "enabled": skill.enabled,
            },
        )
        skill.delete()

    # Delete count skills — counter management is now a built-in command
    Skill.objects.filter(name="count").delete()


def reverse_convert(apps, schema_editor):
    """Reverse: delete converted commands, cannot restore skills."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_add_command_type_and_config"),
    ]

    operations = [
        migrations.RunPython(
            convert_skills_to_commands,
            reverse_convert,
        ),
    ]
