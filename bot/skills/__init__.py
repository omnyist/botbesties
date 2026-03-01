from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import twitchio

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
    pass
