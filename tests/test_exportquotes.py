from __future__ import annotations

import pytest

from core.management.commands.exportquotes import extract_game
from core.management.commands.exportquotes import normalize_quotee
from core.management.commands.exportquotes import parse_ticks


class TestParseTicks:
    def test_valid_ticks(self):
        result = parse_ticks("{ticks: 635760429740000000, kind: 1}")
        assert result is not None
        assert result.year == 2015

    def test_invalid_ticks(self):
        assert parse_ticks("no ticks here") is None

    def test_empty_string(self):
        assert parse_ticks("") is None

    def test_unparseable_ticks(self):
        assert parse_ticks("{ticks: 0, kind: 1}") is not None


class TestNormalizeQuotee:
    def test_spoone_to_spoonee(self):
        assert normalize_quotee("spoone") == "spoonee"

    def test_spooonee_to_spoonee(self):
        assert normalize_quotee("spooonee") == "spoonee"

    def test_spooone_to_spoonee(self):
        assert normalize_quotee("spooone") == "spoonee"

    def test_sponee_to_spoonee(self):
        assert normalize_quotee("sponee") == "spoonee"

    def test_unknown_passes_through(self):
        assert normalize_quotee("kefkafish") == "kefkafish"

    def test_case_insensitive(self):
        assert normalize_quotee("Spoone") == "spoonee"


class TestExtractGame:
    def test_clean_brackets(self):
        text, game = extract_game('I think I\'m lost again... [Final Fantasy IX]')
        assert text == "I think I'm lost again..."
        assert game == "Final Fantasy IX"

    def test_unclosed_bracket(self):
        text, game = extract_game("Something funny [Elden Ring")
        assert text == "Something funny"
        assert game == "Elden Ring"

    def test_unclosed_bracket_with_brace(self):
        text, game = extract_game("Something funny [Elden Ring}")
        assert text == "Something funny"
        assert game == "Elden Ring"

    def test_parentheses_game(self):
        text, game = extract_game("Something funny (Elden Ring)")
        assert text == "Something funny"
        assert game == "Elden Ring"

    def test_parentheses_lowercase_not_game(self):
        text, game = extract_game("I said (lol)")
        assert text == "I said (lol)"
        assert game is None

    def test_dash_game(self):
        text, game = extract_game("Something funny --Elden Ring")
        assert text == "Something funny"
        assert game == "Elden Ring"

    def test_no_game(self):
        text, game = extract_game("Just a regular quote")
        assert text == "Just a regular quote"
        assert game is None

    def test_text_cleaned_after_extraction(self):
        text, game = extract_game("Hello world   [Game]  ")
        assert text == "Hello world"
        assert game == "Game"
