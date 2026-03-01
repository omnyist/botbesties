"""Data migration: update command response variables to new syntax.

$(count) → $(uses)
$(random N-M) → $(random.range N-M)
$(pick a,b,c) → $(random.pick a,b,c)
"""

from __future__ import annotations

import re

from django.db import migrations


def migrate_variables_forward(apps, schema_editor):
    Command = apps.get_model("core", "Command")

    for cmd in Command.objects.all():
        original = cmd.response
        updated = original

        # $(count) → $(uses) — only bare $(count), not $(count.get ...)
        updated = updated.replace("$(count)", "$(uses)")

        # $(random N-M) → $(random.range N-M)
        updated = re.sub(
            r"\$\(random\s+(\d+-\d+)\)",
            r"$(random.range \1)",
            updated,
        )

        # $(pick a,b,c) → $(random.pick a,b,c)
        updated = re.sub(
            r"\$\(pick\s+([^)]+)\)",
            r"$(random.pick \1)",
            updated,
        )

        if updated != original:
            cmd.response = updated
            cmd.save(update_fields=["response"])


def migrate_variables_backward(apps, schema_editor):
    Command = apps.get_model("core", "Command")

    for cmd in Command.objects.all():
        original = cmd.response
        updated = original

        # $(uses) → $(count)
        updated = updated.replace("$(uses)", "$(count)")

        # $(random.range N-M) → $(random N-M)
        updated = re.sub(
            r"\$\(random\.range\s+(\d+-\d+)\)",
            r"$(random \1)",
            updated,
        )

        # $(random.pick a,b,c) → $(pick a,b,c)
        updated = re.sub(
            r"\$\(random\.pick\s+([^)]+)\)",
            r"$(pick \1)",
            updated,
        )

        if updated != original:
            cmd.response = updated
            cmd.save(update_fields=["response"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_alias_counter"),
    ]

    operations = [
        migrations.RunPython(
            migrate_variables_forward,
            migrate_variables_backward,
        ),
    ]
