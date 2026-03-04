from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

# Known Twitch service bots / viewbots that inflate stats.
KNOWN_BOTS = {
    "moobot",
    "nightbot",
    "streamelements",
    "streamlabs",
    "fossabot",
    "wizebot",
    "deepbot",
    "phantombot",
    "botisimo",
    "soundalerts",
    "commanderroot",
    "anotherttvviewer",
    "lurxx",
    "electricallongboard",
    "virgoproz",
    "drapsnatt",
    "streamholics",
    "stay_hydrated_bot",
}


def parse_iso_datetime(value: str) -> datetime | None:
    """Parse an ISO datetime string, returning None on failure."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def format_user(record: dict) -> dict:
    """Convert a raw DeepBot user record to the clean export format."""
    return {
        "username": record["username"].strip().lower(),
        "display_name": record.get("displayName") or None,
        "points": record.get("points", 0.0),
        "minutes_watched": record.get("minutes", 0),
        "first_seen": record.get("firstSeen", ""),
        "last_seen": record.get("lastSeen", ""),
        "access_level": record.get("accessLevel", 10),
    }


class Command(BaseCommand):
    help = "Prune a DeepBot users.json export for Synthfunc import."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file", type=str, help="Path to the DeepBot users.json file."
        )
        parser.add_argument(
            "--min-points",
            type=float,
            default=100,
            help="Minimum points for non-elevated users (default: 100).",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="pruned_users.json",
            help="Output path for pruned user data.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show counts without writing files.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_file"])
        min_points = options["min_points"]
        output_path = Path(options["output"])
        dry_run = options["dry_run"]

        if not json_path.exists():
            raise CommandError(f"File not found: {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Pruning {len(data):,} DeepBot user records"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n  DRY RUN — no files will be written.\n")
            )

        # Step 1: Separate corrupted records (username is not a string)
        valid = []
        corrupted = []
        for record in data:
            if not isinstance(record.get("username"), str):
                corrupted.append(record)
            else:
                valid.append(record)

        corrupted_elevated = [
            r for r in corrupted if r.get("accessLevel", 10) < 10
        ]

        self.stdout.write(
            f"  Corrupted usernames: {len(corrupted):,}"
            f" ({len(corrupted_elevated)} elevated)"
        )

        # Step 2: Trim whitespace and deduplicate
        seen: dict[str, dict] = {}
        dedup_count = 0

        for record in valid:
            username = record["username"].strip().lower()
            if not username:
                continue

            record["username"] = username
            minutes = record.get("minutes", 0)
            points = record.get("points", 0.0)

            if username in seen:
                existing = seen[username]
                existing_minutes = existing.get("minutes", 0)
                existing_points = existing.get("points", 0.0)

                if (minutes, points) > (existing_minutes, existing_points):
                    seen[username] = record
                dedup_count += 1
            else:
                seen[username] = record

        if dedup_count:
            self.stdout.write(f"  Deduplicated: {dedup_count}")

        # Step 3: Filter
        elevated = []
        passed_filter = []
        excluded = []
        bots_removed = []

        for record in seen.values():
            username = record["username"]
            access_level = record.get("accessLevel", 10)

            # Strip known bots regardless of level
            if username in KNOWN_BOTS:
                bots_removed.append(record)
                continue

            # Always keep elevated users
            if access_level < 10:
                elevated.append(record)
                continue

            # Filter non-elevated by points
            points = record.get("points", 0.0)
            if points >= min_points:
                passed_filter.append(record)
            else:
                excluded.append(record)

        kept = elevated + passed_filter

        self.stdout.write(f"\n  Elevated (always kept): {len(elevated)}")
        self.stdout.write(f"  Passed filter (>={min_points} pts): {len(passed_filter)}")
        self.stdout.write(f"  Known bots removed: {len(bots_removed)}")
        self.stdout.write(f"  Excluded: {len(excluded):,}")
        self.stdout.write(
            self.style.SUCCESS(f"  Total kept: {len(kept):,}")
        )

        if not dry_run:
            # Write pruned users (to import)
            output = [format_user(r) for r in kept]
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n  Wrote {len(output):,} users to {output_path}"
                )
            )

            # Write excluded users (lookup for one-off imports)
            excluded_path = output_path.parent / "excluded_users.json"
            excluded_output = [format_user(r) for r in excluded]
            with open(excluded_path, "w", encoding="utf-8") as f:
                json.dump(excluded_output, f, indent=2, ensure_ascii=False)
            self.stdout.write(
                f"  Wrote {len(excluded_output):,} excluded users to {excluded_path}"
            )

            # Write corrupted records for manual review
            corrupted_path = output_path.parent / "corrupted_users.json"
            with open(corrupted_path, "w", encoding="utf-8") as f:
                json.dump(corrupted, f, indent=2, ensure_ascii=False, default=str)
            self.stdout.write(
                f"  Wrote {len(corrupted):,} corrupted records to {corrupted_path}"
            )

        self.stdout.write(self.style.SUCCESS("\nPrune complete."))
