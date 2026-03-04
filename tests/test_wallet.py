from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bot.skills.spoons import SpoonsHandler
from tests.conftest import MockBroadcaster
from tests.conftest import MockChatter
from tests.conftest import MockPayload


@pytest.fixture
def handler():
    return SpoonsHandler()


@pytest.fixture
def bot():
    bot = MagicMock()
    bot.bot_id = "00000"
    return bot


@pytest.fixture
def skill():
    return MagicMock()


class TestSpoonsSkill:
    @pytest.mark.asyncio
    @patch("bot.skills.spoons.get_wallet")
    async def test_own_balance(self, mock_get_wallet, handler, bot, skill):
        mock_get_wallet.return_value = {
            "balance": "525432.5",
            "currency_name": "spoons",
        }
        payload = MockPayload(text="!spoons")
        await handler.handle(payload, "", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "525,432.5 spoons" in msg
        assert "@TestUser" in msg

    @pytest.mark.asyncio
    @patch("bot.skills.spoons.get_wallet")
    async def test_target_balance(self, mock_get_wallet, handler, bot, skill):
        mock_get_wallet.return_value = {
            "balance": "171661.0",
            "currency_name": "spoons",
        }

        mock_user = MagicMock()
        mock_user.id = 55555
        mock_user.display_name = "kefkafish"
        mock_user.name = "kefkafish"
        bot.fetch_users = AsyncMock(return_value=[mock_user])

        payload = MockPayload(text="!spoons @kefka")
        await handler.handle(payload, "@kefka", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "171,661 spoons" in msg
        assert "@kefkafish" in msg

    @pytest.mark.asyncio
    @patch("bot.skills.spoons.get_wallet")
    async def test_no_wallet(self, mock_get_wallet, handler, bot, skill):
        mock_get_wallet.return_value = None
        payload = MockPayload(text="!spoons")
        await handler.handle(payload, "", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "doesn't have a wallet" in msg

    @pytest.mark.asyncio
    async def test_unknown_twitch_user(self, handler, bot, skill):
        bot.fetch_users = AsyncMock(return_value=[])
        payload = MockPayload(text="!spoons @nobody")
        await handler.handle(payload, "@nobody", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "Could not find" in msg

    @pytest.mark.asyncio
    @patch("bot.skills.spoons.get_wallet")
    async def test_whole_number_no_decimal(
        self, mock_get_wallet, handler, bot, skill
    ):
        mock_get_wallet.return_value = {
            "balance": "1000.0",
            "currency_name": "spoons",
        }
        payload = MockPayload(text="!spoons")
        await handler.handle(payload, "", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "1,000 spoons" in msg

    @pytest.mark.asyncio
    @patch("bot.skills.spoons.get_wallet")
    async def test_zero_balance(self, mock_get_wallet, handler, bot, skill):
        mock_get_wallet.return_value = {
            "balance": "0",
            "currency_name": "points",
        }
        payload = MockPayload(text="!spoons")
        await handler.handle(payload, "", skill, bot)

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "0 points" in msg


class TestQuoteFormat:
    def test_format_with_game_and_year(self):
        from bot.skills.quotes import _format_quote

        quote = {
            "number": 42,
            "text": "I think I'm lost again...",
            "quotee": {"display_name": "Spoonee", "username": "spoonee"},
            "game": "Final Fantasy IX",
            "year": 2015,
        }
        result = _format_quote(quote)
        assert result == (
            'Quote #42: "I think I\'m lost again..." '
            "— Spoonee [Final Fantasy IX, 2015]"
        )

    def test_format_with_game_no_year(self):
        from bot.skills.quotes import _format_quote

        quote = {
            "number": 1,
            "text": "Hello!",
            "quotee": {"display_name": "Test"},
            "game": "Elden Ring",
            "year": None,
        }
        result = _format_quote(quote)
        assert result == 'Quote #1: "Hello!" — Test [Elden Ring]'

    def test_format_with_year_no_game(self):
        from bot.skills.quotes import _format_quote

        quote = {
            "number": 1,
            "text": "Hello!",
            "quotee": {"display_name": "Test"},
            "game": None,
            "year": 2024,
        }
        result = _format_quote(quote)
        assert result == 'Quote #1: "Hello!" — Test [2024]'

    def test_format_no_game_no_year(self):
        from bot.skills.quotes import _format_quote

        quote = {
            "number": 1,
            "text": "Hello!",
            "quotee": {"display_name": "Test"},
        }
        result = _format_quote(quote)
        assert result == 'Quote #1: "Hello!" — Test'
