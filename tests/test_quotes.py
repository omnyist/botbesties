from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bot.skills.quotes import QuoteHandler
from bot.skills.quotes import _format_quote
from tests.conftest import MockPayload


@pytest.fixture
def handler():
    return QuoteHandler()


@pytest.fixture
def bot():
    bot = MagicMock()
    bot.bot_id = "00000"
    return bot


@pytest.fixture
def skill():
    skill = MagicMock()
    skill.channel.twitch_channel_name = "testchannel"
    return skill


class TestQuoteAdd:
    @pytest.mark.asyncio
    @patch("bot.skills.quotes.create_quote")
    async def test_add_valid_format(self, mock_create, handler, bot, skill):
        mock_create.return_value = {"number": 99}
        handler._get_current_game = AsyncMock(return_value="Final Fantasy IX")
        payload = MockPayload(text='!quote add "Something funny" ~ @spoonee')
        await handler.handle(payload, 'add "Something funny" ~ @spoonee', skill, bot)

        mock_create.assert_called_once_with(
            "Something funny", "spoonee", "TestUser", "testchannel",
            game="Final Fantasy IX",
        )
        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "added quote #99" in msg
        assert "Blame yourself or God." in msg

    @pytest.mark.asyncio
    async def test_add_bad_format_shows_ocd_message(self, handler, bot, skill):
        payload = MockPayload(text="!quote add @spoonee Something funny")
        await handler.handle(payload, "add @spoonee Something funny", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "OCD" in msg
        assert '"quote" ~ @username' in msg

    @pytest.mark.asyncio
    async def test_add_no_args(self, handler, bot, skill):
        payload = MockPayload(text="!quote add")
        await handler.handle(payload, "add", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Usage:" in msg

    @pytest.mark.asyncio
    @patch("bot.skills.quotes.create_quote")
    async def test_add_preserves_quote_text(self, mock_create, handler, bot, skill):
        mock_create.return_value = {"number": 100}
        handler._get_current_game = AsyncMock(return_value=None)
        payload = MockPayload(
            text='!quote add "I can\'t believe it\'s not butter!" ~ @bryan'
        )
        await handler.handle(
            payload,
            'add "I can\'t believe it\'s not butter!" ~ @bryan',
            skill,
            bot,
        )

        mock_create.assert_called_once_with(
            "I can't believe it's not butter!", "bryan", "TestUser", "testchannel",
            game=None,
        )


class TestQuoteFormat:
    def test_format_with_game_and_year(self):
        quote = {
            "number": 42,
            "text": "I think I'm lost again...",
            "quotee": {"display_name": "Spoonee", "username": "spoonee"},
            "game": "Final Fantasy IX",
            "year": 2015,
        }
        result = _format_quote(quote)
        assert result == (
            '"I think I\'m lost again..." '
            "~ Spoonee (#42, 2015, Final Fantasy IX)"
        )

    def test_format_with_game_no_year(self):
        quote = {
            "number": 1,
            "text": "Hello!",
            "quotee": {"display_name": "Test"},
            "game": "Elden Ring",
            "year": None,
        }
        result = _format_quote(quote)
        assert result == '"Hello!" ~ Test (#1, Elden Ring)'

    def test_format_with_year_no_game(self):
        quote = {
            "number": 1,
            "text": "Hello!",
            "quotee": {"display_name": "Test"},
            "game": None,
            "year": 2024,
        }
        result = _format_quote(quote)
        assert result == '"Hello!" ~ Test (#1, 2024)'

    def test_format_no_game_no_year(self):
        quote = {
            "number": 1,
            "text": "Hello!",
            "quotee": {"display_name": "Test"},
        }
        result = _format_quote(quote)
        assert result == '"Hello!" ~ Test (#1)'
