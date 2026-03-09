from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from bot.skills import SKILL_REGISTRY
from bot.skills import discover_skills
from bot.skills.markov import MarkovHandler
from bot.skills.markov import build_chain
from bot.skills.markov import generate_sentence
from bot.skills.markov import END
from bot.skills.markov import START
from tests.conftest import MockChatter
from tests.conftest import MockPayload


class TestBuildChain:
    def test_basic_transitions(self):
        messages = ["the quick brown fox jumps"]
        chain = build_chain(messages)

        assert START in chain
        assert "the" in chain[START]
        assert "quick" in chain["the"]
        assert "brown" in chain["quick"]
        assert END in chain["jumps"]

    def test_skips_short_messages(self):
        messages = ["hi", "yes no", "this is long enough"]
        chain = build_chain(messages)

        assert len(chain) > 0
        all_values = [v for vals in chain.values() for v in vals]
        assert "hi" not in all_values

    def test_empty_messages(self):
        chain = build_chain([])
        assert chain == {}

    def test_multiple_messages_merge(self):
        messages = [
            "I love cats very much",
            "I love dogs very much",
        ]
        chain = build_chain(messages)

        assert "cats" in chain["love"]
        assert "dogs" in chain["love"]
        assert len(chain[START]) == 2


class TestGenerateSentence:
    def test_generates_from_chain(self):
        messages = [
            "the quick brown fox jumps over the lazy dog today",
        ]
        chain = build_chain(messages)
        sentence = generate_sentence(chain)

        assert sentence is not None
        assert len(sentence.split()) >= 2

    def test_empty_chain_returns_none(self):
        assert generate_sentence({}) is None

    def test_respects_max_words(self):
        messages = ["a b c d e f g h i j k l m n o p q r s t u v w x y z aa bb"]
        chain = build_chain(messages)
        sentence = generate_sentence(chain, max_words=5)

        assert sentence is not None
        assert len(sentence.split()) <= 5

    def test_deterministic_with_seed(self):
        import random as rng

        messages = ["hello world this is a test message for markov chains"]
        chain = build_chain(messages)

        rng.seed(42)
        s1 = generate_sentence(chain)
        rng.seed(42)
        s2 = generate_sentence(chain)
        assert s1 == s2


class TestMarkovRegistry:
    def test_markov_in_registry(self):
        discover_skills()
        assert "markov" in SKILL_REGISTRY
        assert isinstance(SKILL_REGISTRY["markov"], MarkovHandler)


def _mock_bot():
    bot = MagicMock()
    bot.bot_id = "00000"
    return bot


def _mock_skill(channel_name="spoonee"):
    skill = MagicMock()
    skill.channel.twitch_channel_name = channel_name
    skill.config = {}
    return skill


class TestMarkovHandler:
    @pytest.fixture()
    def handler(self):
        return MarkovHandler()

    @pytest.mark.asyncio
    @patch("bot.skills.markov.aioredis")
    async def test_generate_from_cache(self, mock_aioredis, handler):
        import json

        chain = build_chain(["the quick brown fox jumps over the lazy dog today"])
        mock_client = AsyncMock()
        mock_client.get.return_value = json.dumps(chain).encode()
        mock_aioredis.from_url.return_value = mock_client

        payload = MockPayload(text="!markov")
        await handler.handle(payload, "", _mock_skill(), _mock_bot())

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert len(msg) > 0

    @pytest.mark.asyncio
    @patch("bot.skills.markov.aioredis")
    @patch("bot.skills.markov.get_chat_messages")
    async def test_builds_on_cache_miss(
        self, mock_messages, mock_aioredis, handler
    ):
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mock_messages.return_value = [
            "the quick brown fox jumps over the lazy dog today",
            "I really love playing video games all day",
            "chat is being really funny right now honestly",
        ]

        payload = MockPayload(text="!markov")
        await handler.handle(payload, "", _mock_skill(), _mock_bot())

        mock_client.set.assert_called_once()
        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert len(msg) > 0

    @pytest.mark.asyncio
    @patch("bot.skills.markov.aioredis")
    @patch("bot.skills.markov.get_chat_messages")
    async def test_rebuild_subcommand_mod_only(
        self, mock_messages, mock_aioredis, handler
    ):
        mock_client = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        mock_messages.return_value = [
            "hello world this is a test chat message",
        ]

        payload = MockPayload(
            text="!markov rebuild",
            chatter=MockChatter(moderator=True),
        )
        await handler.handle(payload, "rebuild", _mock_skill(), _mock_bot())

        mock_client.set.assert_called_once()
        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "rebuilt" in msg.lower()

    @pytest.mark.asyncio
    async def test_rebuild_denied_for_non_mod(self, handler):
        payload = MockPayload(
            text="!markov rebuild",
            chatter=MockChatter(moderator=False, broadcaster=False),
        )
        await handler.handle(payload, "rebuild", _mock_skill(), _mock_bot())

        payload.broadcaster.send_message.assert_not_called()

    @pytest.mark.asyncio
    @patch("bot.skills.markov.aioredis")
    @patch("bot.skills.markov.get_chat_messages")
    async def test_no_data_shows_message(
        self, mock_messages, mock_aioredis, handler
    ):
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mock_messages.return_value = None

        payload = MockPayload(text="!markov")
        await handler.handle(payload, "", _mock_skill(), _mock_bot())

        msg = payload.broadcaster.send_message.call_args.kwargs["message"]
        assert "not enough" in msg.lower()
