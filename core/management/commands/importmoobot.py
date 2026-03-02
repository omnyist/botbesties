from __future__ import annotations

import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from core.models import Alias
from core.models import Channel
from core.models import Command as CommandModel
from core.models import Counter

# Moobot variables → Botbesties variable replacements
VARIABLE_MAP = {
    "<username>": "$(user)",
    "<args>": "$(target)",
    "<twitch.game>": "$(game)",
    "<twitch.uptime>": "$(uptime)",
}

# Moobot variables that can't be converted — commands using these are skipped
UNSUPPORTED_VARIABLES = {"<time>", "<twitch.followed>"}

# Pattern to detect <counter> in Moobot command text
COUNTER_PATTERN = re.compile(r"<counter>")


def convert_variables(text: str) -> str:
    """Replace Moobot variables with Botbesties equivalents."""
    for moobot_var, bb_var in VARIABLE_MAP.items():
        text = text.replace(moobot_var, bb_var)
    return text


def has_unsupported_variables(text: str) -> list[str]:
    """Return list of unsupported Moobot variables found in text."""
    found = []
    for var in UNSUPPORTED_VARIABLES:
        if var in text:
            found.append(var)
    return found


def uses_counter(text: str) -> bool:
    """Check if the command text uses the Moobot <counter> variable."""
    return bool(COUNTER_PATTERN.search(text))


class Command(BaseCommand):
    help = "Import commands from a Moobot export JSON file into a channel."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file", type=str, help="Path to the Moobot export JSON file."
        )
        parser.add_argument(
            "--channel",
            type=str,
            required=True,
            help="Twitch channel name to import into.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without saving.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_file"])
        channel_name = options["channel"].lower()
        dry_run = options["dry_run"]

        if not json_path.exists():
            raise CommandError(f"File not found: {json_path}")

        with open(json_path, encoding="utf-8-sig") as f:
            data = json.load(f)

        try:
            channel = Channel.objects.get(twitch_channel_name=channel_name)
        except Channel.DoesNotExist:
            raise CommandError(f"Channel not found: #{channel_name}")

        # Find the commands_custom section in the Moobot export
        moobot_commands = None
        for setting in data.get("settings", []):
            if setting.get("type") == "commands_custom":
                moobot_commands = setting["data"]
                break

        if moobot_commands is None:
            raise CommandError(
                "No 'commands_custom' section found in the Moobot export."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Importing {len(moobot_commands)} Moobot commands"
                f" into #{channel_name}"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n  DRY RUN — no changes will be saved.\n")
            )

        created_count = 0
        skipped_count = 0
        counter_count = 0
        alias_count = 0
        unsupported_count = 0

        for cmd in moobot_commands:
            name = cmd["identifier"]
            enabled = cmd["enabled"]
            moobot_counter = cmd.get("counter", 0)

            # Determine effective text: mod-editable commands use chat_text
            mod_editable = cmd.get("mod_editable", False)
            chat_text = cmd.get("chat_text", "")
            raw_text = chat_text if (mod_editable and chat_text) else cmd["text"]

            # --- Skip: commands whose entire text is a Moobot built-in ---

            # <twitch.followed> → alias to !followage
            if "<twitch.followed>" in raw_text:
                if not dry_run:
                    Alias.objects.get_or_create(
                        channel=channel,
                        name=name,
                        defaults={"target": "followage"},
                    )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Alias: !{name} → !followage (Moobot followage)"
                    )
                )
                alias_count += 1
                continue

            # Check for unsupported variables
            unsupported = has_unsupported_variables(raw_text)
            if unsupported:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Skipped: !{name}"
                        f" (unsupported: {', '.join(unsupported)})"
                    )
                )
                unsupported_count += 1
                continue

            # --- Check if command already exists ---
            existing = CommandModel.objects.filter(
                channel=channel, name=name
            ).first()
            if existing:
                skipped_count += 1
                self.stdout.write(f"  Skipped (exists): !{name}")
                continue

            # --- Handle counter-based commands ---
            if uses_counter(raw_text):
                # Replace <counter> with $(count.get <name>)
                response = raw_text.replace(
                    "<counter>", f"$(count.get {name})"
                )
                response = convert_variables(response)

                if not dry_run:
                    CommandModel.objects.create(
                        channel=channel,
                        name=name,
                        response=response,
                        enabled=enabled,
                        use_count=moobot_counter,
                        created_by=channel_name,
                    )
                    # Create the Counter with the preserved Moobot value
                    Counter.objects.get_or_create(
                        channel=channel,
                        name=name,
                        defaults={
                            "value": moobot_counter,
                            "label": name.title(),
                        },
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created: !{name}"
                        f" + counter (value={moobot_counter})"
                    )
                )
                created_count += 1
                counter_count += 1
                continue

            # --- Standard text command ---
            response = convert_variables(raw_text)

            if not dry_run:
                CommandModel.objects.create(
                    channel=channel,
                    name=name,
                    response=response,
                    enabled=enabled,
                    use_count=moobot_counter,
                    created_by=channel_name,
                )

            status = "Created" if enabled else "Created (disabled)"
            self.stdout.write(self.style.SUCCESS(f"  {status}: !{name}"))
            created_count += 1

        # --- Summary ---
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  Commands created: {created_count}"))
        if counter_count:
            self.stdout.write(f"  Counters created: {counter_count}")
        if alias_count:
            self.stdout.write(f"  Aliases created: {alias_count}")
        if skipped_count:
            self.stdout.write(f"  Skipped (already exist): {skipped_count}")
        if unsupported_count:
            self.stdout.write(
                self.style.WARNING(
                    f"  Skipped (unsupported variables): {unsupported_count}"
                )
            )

        self.stdout.write(self.style.SUCCESS("\nMoobot import complete."))
