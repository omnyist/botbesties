from __future__ import annotations

import json
import re
from datetime import datetime
from datetime import timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

# .NET ticks epoch offset (ticks between 0001-01-01 and 1970-01-01)
DOTNET_EPOCH_OFFSET = 621355968000000000
TICKS_PER_SECOND = 10_000_000

TICKS_PATTERN = re.compile(r"ticks:\s*(\d+)")

# Clean: [Game Name] at end of text
GAME_CLEAN_PATTERN = re.compile(r"\s*\[([^\]]+)\]\s*$")

# Unclosed: [Game Name at end (may have trailing } or [)
GAME_UNCLOSED_PATTERN = re.compile(r"\s*\[([^\]]+?)\s*$")

# Alternate: (Game Name) at end
GAME_PAREN_PATTERN = re.compile(r"\s*\(([^)]+)\)\s*$")

# Alternate: --Game Name at end
GAME_DASH_PATTERN = re.compile(r"\s*--\s*(.+?)\s*$")

# Quotee name normalizations (typo variants)
QUOTEE_FIXES = {
    "spoone": "spoonee",
    "spooonee": "spoonee",
    "spooone": "spoonee",
    "sponee": "spoonee",
}


def parse_ticks(ticks_str: str) -> datetime | None:
    """Parse a .NET ticks string like '{ticks: 635760429740000000, kind: ...}'."""
    match = TICKS_PATTERN.search(ticks_str)
    if not match:
        return None
    ticks = int(match.group(1))
    try:
        unix_seconds = (ticks - DOTNET_EPOCH_OFFSET) / TICKS_PER_SECOND
        return datetime.fromtimestamp(unix_seconds, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def extract_game(text: str) -> tuple[str, str | None]:
    """Extract game name from quote text.

    Returns (cleaned_text, game_name_or_none).
    """
    # Try clean brackets first: [Game Name]
    match = GAME_CLEAN_PATTERN.search(text)
    if match:
        game = match.group(1).strip()
        cleaned = text[: match.start()].rstrip()
        return cleaned, game

    # Try unclosed bracket: [Game Name (strip trailing } or [)
    match = GAME_UNCLOSED_PATTERN.search(text)
    if match:
        game = match.group(1).strip().rstrip("}[").strip()
        cleaned = text[: match.start()].rstrip()
        if game:
            return cleaned, game

    # Try parentheses: (Game Name)
    match = GAME_PAREN_PATTERN.search(text)
    if match:
        candidate = match.group(1).strip()
        # Only treat as game if it looks like a title (starts with uppercase)
        if candidate and candidate[0].isupper():
            cleaned = text[: match.start()].rstrip()
            return cleaned, candidate

    # Try dash separator: --Game Name
    match = GAME_DASH_PATTERN.search(text)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate[0].isupper():
            cleaned = text[: match.start()].rstrip()
            return cleaned, candidate

    return text.rstrip(), None


def normalize_quotee(name: str) -> str:
    """Fix known quotee name typos."""
    return QUOTEE_FIXES.get(name.lower(), name.lower())


class Command(BaseCommand):
    help = "Export quotes from a DeepBot chanmsgconfig.json for Synthfunc import."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_file",
            type=str,
            help="Path to the DeepBot chanmsgconfig.json file.",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="quotes_export.json",
            help="Output path for exported quotes.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json_file"])
        output_path = Path(options["output"])

        if not json_path.exists():
            raise CommandError(f"File not found: {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        raw_quotes = data.get("quoteMessages")
        if raw_quotes is None:
            raise CommandError("No 'quoteMessages' key found in the JSON file.")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Exporting {len(raw_quotes):,} quotes"
            )
        )

        exported = []
        no_game = []
        normalization_count = 0

        for q in raw_quotes:
            number = q["Num"]
            raw_text = q["Msg"]
            quotee = q.get("User", "unknown")
            quoter = q.get("addedBy", "unknown")
            added_on_str = q.get("addedOn", "")

            # Parse date from .NET ticks
            added_dt = parse_ticks(added_on_str)
            year = added_dt.year if added_dt else None
            added_on_iso = added_dt.isoformat() if added_dt else None

            # Normalize quotee name
            normalized = normalize_quotee(quotee)
            if normalized != quotee.lower():
                normalization_count += 1
            quotee = normalized

            # Extract game from text
            cleaned_text, game = extract_game(raw_text)

            if game is None:
                no_game.append(number)

            exported.append({
                "number": number,
                "text": cleaned_text,
                "game": game,
                "quotee_username": quotee,
                "quoter_username": quoter.lower(),
                "year": year,
                "added_on": added_on_iso,
            })

        # Write output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(exported, f, indent=2, ensure_ascii=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Wrote {len(exported):,} quotes to {output_path}"
            )
        )

        with_game = len(exported) - len(no_game)
        self.stdout.write(f"  With game: {with_game}")
        self.stdout.write(f"  Without game: {len(no_game)}")

        if normalization_count:
            self.stdout.write(f"  Quotee names normalized: {normalization_count}")

        if no_game:
            self.stdout.write(
                self.style.WARNING("\n  Quotes without game (review manually):")
            )
            for num in no_game:
                q = next(q for q in raw_quotes if q["Num"] == num)
                preview = q["Msg"][:80]
                self.stdout.write(f"    #{num}: {preview}")

        self.stdout.write(self.style.SUCCESS("\nExport complete."))
