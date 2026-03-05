from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import twitchio
    from twitchio.ext import commands

    from core.models import Skill

logger = logging.getLogger("bot")


class SkillHandler:
    """Base class for skill implementations.

    Each handler owns a skill name that matches a Skill.name in the DB.
    The CommandRouter dispatches to the handler when a matching skill
    is found and enabled for the channel.
    """

    name: str = ""

    async def handle(
        self,
        payload: twitchio.ChatMessage,
        args: str,
        skill: Skill,
        bot: commands.Bot,
    ) -> None:
        raise NotImplementedError


SKILL_REGISTRY: dict[str, SkillHandler] = {}


def register_skill(handler: SkillHandler) -> None:
    """Register a skill handler by name."""
    SKILL_REGISTRY[handler.name] = handler
    logger.debug("Registered skill handler: %s", handler.name)


def discover_skills() -> None:
    """Import all skill modules to trigger registration.

    Simple behaviors (conch, flask, counter) are now command types
    handled inline by the router. This function registers only
    complex Python-coded skill handlers.
    """
    from bot.skills import campaigns  # noqa: F401
    from bot.skills import dungeon  # noqa: F401
    from bot.skills import followcheck  # noqa: F401
    from bot.skills import lizardroulette  # noqa: F401
    from bot.skills import quotes  # noqa: F401
    from bot.skills import wallet  # noqa: F401
