from __future__ import annotations

import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError


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
            "--min-minutes",
            type=int,
            default=60,
            help="Minimum minutes watched for non-elevated users (default: 60).",
        )
        parser.add_argument(
            "--max-inactive-days",
            type=int,
            default=730,
            help="Max days since last seen for non-elevated users (default: 730).",
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
        min_minutes = options["min_minutes"]
        max_inactive_days = options["max_inactive_days"]
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

        # Step 3: Separate elevated and non-elevated
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(days=max_inactive_days)

        elevated = []
        passed_filter = []
        filtered_out = 0

        for record in seen.values():
            access_level = record.get("accessLevel", 10)

            if access_level < 10:
                elevated.append(record)
                continue

            minutes = record.get("minutes", 0)
            if minutes < min_minutes:
                filtered_out += 1
                continue

            last_seen = parse_iso_datetime(record.get("lastSeen", ""))
            if last_seen is None or last_seen < cutoff:
                filtered_out += 1
                continue

            passed_filter.append(record)

        kept = elevated + passed_filter

        self.stdout.write(f"  Elevated (always kept): {len(elevated)}")
        self.stdout.write(f"  Passed filter: {len(passed_filter)}")
        self.stdout.write(f"  Filtered out: {filtered_out}")
        self.stdout.write(
            self.style.SUCCESS(f"  Total kept: {len(kept):,}")
        )

        if not dry_run:
            # Write pruned users
            output = [format_user(r) for r in kept]
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            self.stdout.write(
                self.style.SUCCESS(f"\n  Wrote {len(output):,} users to {output_path}")
            )

            # Write corrupted records for manual review
            corrupted_path = output_path.parent / "corrupted_users.json"
            with open(corrupted_path, "w", encoding="utf-8") as f:
                json.dump(corrupted, f, indent=2, ensure_ascii=False, default=str)
            self.stdout.write(
                f"  Wrote {len(corrupted):,} corrupted records to {corrupted_path}"
            )

        self.stdout.write(self.style.SUCCESS("\nPrune complete."))
