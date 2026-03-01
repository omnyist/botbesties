from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from core.models import Channel
from core.models import Command as CommandModel


class Command(BaseCommand):
    help = "Import commands from a JSON file into a channel."

    def add_arguments(self, parser):
        parser.add_argument("json_file", type=str, help="Path to the JSON file.")
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

        with open(json_path) as f:
            data = json.load(f)

        try:
            channel = Channel.objects.get(twitch_channel_name=channel_name)
        except Channel.DoesNotExist:
            raise CommandError(f"Channel not found: #{channel_name}")

        commands_data = data.get("commands", [])
        metadata = data.get("metadata", {})

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Importing {len(commands_data)} commands into #{channel_name}"
            )
        )

        if metadata:
            self.stdout.write(f"  Source: {metadata.get('total_in_excel', '?')} total in file")
            skipped = metadata.get("skipped_skills", [])
            if skipped:
                self.stdout.write(f"  Skills skipped: {', '.join(skipped)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n  DRY RUN — no changes will be saved.\n"))

        created_count = 0
        skipped_count = 0
        updated_count = 0

        for cmd_data in commands_data:
            name = cmd_data["name"]
            response = cmd_data["response"]
            mod_only = cmd_data.get("mod_only", False)

            existing = CommandModel.objects.filter(channel=channel, name=name).first()

            if existing:
                skipped_count += 1
                self.stdout.write(f"  Skipped (exists): !{name}")
                continue

            if not dry_run:
                CommandModel.objects.create(
                    channel=channel,
                    name=name,
                    response=response,
                    mod_only=mod_only,
                    created_by="import",
                )

            created_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"  Created: {created_count}")
        )
        if skipped_count:
            self.stdout.write(f"  Skipped (already exist): {skipped_count}")
        if updated_count:
            self.stdout.write(f"  Updated: {updated_count}")

        self.stdout.write(self.style.SUCCESS("\nImport complete."))
