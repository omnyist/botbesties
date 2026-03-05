"""!dungeon — Multiplayer dungeon minigame with currency wagering.

Usage:
    !dungeon 500   — Start or join a dungeon run, wagering 500 spoons
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass
from dataclasses import field

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.synthfunc import transact_wallets

logger = logging.getLogger("bot")

DEFAULT_LEVELS = [
    {"name": "Cactuar Village", "min_players": 1, "survival_chance": 70, "multiplier": 1.5},
    {"name": "Tonberry Cove", "min_players": 3, "survival_chance": 60, "multiplier": 1.75},
    {"name": "Ultros", "min_players": 6, "survival_chance": 50, "multiplier": 2.0},
    {"name": "Tiamat", "min_players": 12, "survival_chance": 40, "multiplier": 2.25},
    {"name": "Bahamut", "min_players": 18, "survival_chance": 30, "multiplier": 2.5},
]

DEFAULT_MESSAGES = {
    "entry_started": (
        "$(user) is looking for a party to explore the Dungeon, wagering $(wager) $(currency)! "
        "To join, type !dungeon (amount). You have $(entry_duration)s to join!"
    ),
    "entry_joined": "$(user) joins the party, wagering $(wager) $(currency)! ($(count) adventurers)",
    "entry_closed": (
        "It has begun! The party stocks up on potions and readies their equipment before "
        "leaving town. They head straight into $(level_name)!"
    ),
    "outcome_wipe": (
        "The party boldly enters the Dungeon...but they are ill prepared. "
        "They barely make it past the first room when the entire party is MPKed... bardRIP "
        "It looks like $(level_name) knew they were coming. bardSad"
    ),
    "outcome_few": (
        "The party doesn't get far into the Dungeon when they are Back Attacked by the "
        "worst enemy of all...RNG! bardD Most of the party falls prey to RNG's clutches, "
        "but a few lucky survivors Flee and make it back to town safely."
    ),
    "outcome_most": (
        "Some of the party fall prey to Random Battles, but those who remain reach "
        "$(level_name)! They raise their Weapons of Magic and Might...and they scrape by! "
        "bardHype It was a rough fight. They resolve to exit the Dungeon and return another day."
    ),
    "outcome_all": (
        "The party reaches $(level_name)! They raise their Weapons of Magic and Might..."
        "and they are successful! bardHype The party is balanced well and ready for the fight. "
        "$(level_name) is clear (for now...)! Victory and treasure for all!"
    ),
    "outcome_solo_win": (
        "$(user) dares to enter $(level_name) alone...and they are successful! bardOMG "
        "$(user) sneaks in and out, looting treasure chests! Looted $(payout) $(currency)."
    ),
    "outcome_solo_loss": (
        "$(user) dares to enter $(level_name) alone...and they are unlucky! bardSad "
        "$(user) trips in the treasure room and finds an awakened Malboro. Game over. bardRIP"
    ),
    "results_winners": "Survivors: $(winner_list) — Payout: $(total_payout) $(currency).",
    "results_losers": "Fallen: $(loser_list). bardRIP",
    "insufficient_funds": "$(user), you don't have enough $(currency) for that wager.",
    "already_joined": "$(user), you're already in the party!",
    "cooldown_response": (
        "Tiamat is patrolling the area around town. We better wait for a bit! "
        "Cooldown: $(remaining)s."
    ),
    "no_wager": "$(user), you need to specify a wager! Usage: !dungeon (amount)",
    "invalid_wager": "$(user), wager must be a number between $(min_wager) and $(max_wager).",
    "late_entry": (
        "Sorry $(user), you are too late. The party has already left for the Dungeon. "
        "It's too dangerous to go alone."
    ),
    "level_up": "With this party, we can now venture into $(level_name)!",
}


@dataclass
class DungeonParticipant:
    twitch_id: str
    display_name: str
    username: str
    wager: int
    survived: bool = False


@dataclass
class DungeonGame:
    broadcaster_id: str
    channel_name: str
    broadcaster: object
    bot_id: str | int
    participants: dict[str, DungeonParticipant] = field(default_factory=dict)
    phase: str = "entry"
    task: asyncio.Task | None = None


class DungeonHandler(SkillHandler):
    """!dungeon — Multiplayer dungeon minigame with currency wagering."""

    name = "dungeon"

    def __init__(self):
        self._games: dict[str, DungeonGame] = {}
        self._cooldowns: dict[str, float] = {}

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        if not chatter:
            return

        config = skill.config or {}
        broadcaster_id = str(payload.broadcaster.id)
        chatter_id = str(chatter.id)
        chatter_name = chatter.display_name
        username = chatter.name
        channel_name = skill.channel.twitch_channel_name
        messages = config.get("messages", DEFAULT_MESSAGES)
        currency = config.get("currency_name", "spoons")
        min_wager = config.get("min_wager", 10)
        max_wager = config.get("max_wager", 10000)

        game = self._games.get(broadcaster_id)

        # --- On cooldown ---
        cooldown = config.get("cooldown", 900)
        now = time.monotonic()
        last_completed = self._cooldowns.get(broadcaster_id)
        if game is None and last_completed and (now - last_completed) < cooldown:
            remaining = int(cooldown - (now - last_completed))
            msg = messages.get("cooldown_response", DEFAULT_MESSAGES["cooldown_response"])
            msg = msg.replace("$(remaining)", str(remaining))
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        # --- Running phase — ignore ---
        if game and game.phase == "running":
            return

        # --- Late entry ---
        if game and game.phase != "entry":
            msg = messages.get("late_entry", DEFAULT_MESSAGES["late_entry"])
            msg = msg.replace("$(user)", chatter_name)
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        # --- Already joined ---
        if game and chatter_id in game.participants:
            msg = messages.get("already_joined", DEFAULT_MESSAGES["already_joined"])
            msg = msg.replace("$(user)", chatter_name)
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        # --- Parse wager ---
        if not args or not args.strip():
            msg = messages.get("no_wager", DEFAULT_MESSAGES["no_wager"])
            msg = msg.replace("$(user)", chatter_name)
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        try:
            wager = int(args.strip())
        except ValueError:
            msg = messages.get("invalid_wager", DEFAULT_MESSAGES["invalid_wager"])
            msg = (
                msg.replace("$(user)", chatter_name)
                .replace("$(min_wager)", str(min_wager))
                .replace("$(max_wager)", str(max_wager))
            )
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        if wager < min_wager or wager > max_wager:
            msg = messages.get("invalid_wager", DEFAULT_MESSAGES["invalid_wager"])
            msg = (
                msg.replace("$(user)", chatter_name)
                .replace("$(min_wager)", str(min_wager))
                .replace("$(max_wager)", str(max_wager))
            )
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        # --- Deduct wager ---
        result = await transact_wallets(
            channel_name,
            [{"twitch_id": chatter_id, "amount": str(-wager), "username": username, "display_name": chatter_name}],
            reason="dungeon_entry",
        )
        if result is None or result.get("processed", 0) == 0:
            failed = result.get("failed", []) if result else []
            error = failed[0].get("error", "") if failed else ""
            if error == "insufficient_funds":
                msg = messages.get("insufficient_funds", DEFAULT_MESSAGES["insufficient_funds"])
            else:
                msg = messages.get("insufficient_funds", DEFAULT_MESSAGES["insufficient_funds"])
            msg = msg.replace("$(user)", chatter_name).replace("$(currency)", currency)
            await send_reply(payload, msg, bot_id=bot.bot_id)
            return

        participant = DungeonParticipant(
            twitch_id=chatter_id,
            display_name=chatter_name,
            username=username,
            wager=wager,
        )

        # --- Start new game ---
        if game is None:
            game = DungeonGame(
                broadcaster_id=broadcaster_id,
                channel_name=channel_name,
                broadcaster=payload.broadcaster,
                bot_id=bot.bot_id,
            )
            game.participants[chatter_id] = participant
            self._games[broadcaster_id] = game

            entry_duration = config.get("entry_duration", 120)
            msg = messages.get("entry_started", DEFAULT_MESSAGES["entry_started"])
            msg = (
                msg.replace("$(user)", chatter_name)
                .replace("$(wager)", str(wager))
                .replace("$(currency)", currency)
                .replace("$(entry_duration)", str(entry_duration))
            )
            await send_reply(payload, msg, bot_id=bot.bot_id)

            game.task = asyncio.create_task(
                self._run_dungeon(game, config)
            )
            return

        # --- Join existing game ---
        game.participants[chatter_id] = participant
        game.broadcaster = payload.broadcaster

        count = len(game.participants)
        msg = messages.get("entry_joined", DEFAULT_MESSAGES["entry_joined"])
        msg = (
            msg.replace("$(user)", chatter_name)
            .replace("$(wager)", str(wager))
            .replace("$(currency)", currency)
            .replace("$(count)", str(count))
        )
        await send_reply(payload, msg, bot_id=bot.bot_id)

        # --- Level-up announcement ---
        levels = config.get("levels", DEFAULT_LEVELS)
        prev_level = self._get_level(count - 1, levels)
        curr_level = self._get_level(count, levels)
        if curr_level and prev_level and curr_level["name"] != prev_level["name"]:
            level_msg = messages.get("level_up", DEFAULT_MESSAGES["level_up"])
            level_msg = level_msg.replace("$(level_name)", curr_level["name"])
            try:
                await game.broadcaster.send_message(
                    sender=game.bot_id, message=level_msg
                )
            except Exception:
                logger.exception("Failed to send level-up message")

    async def _run_dungeon(self, game: DungeonGame, config: dict) -> None:
        """Entry timer → resolve dungeon → pay out winners."""
        entry_duration = config.get("entry_duration", 120)
        messages = config.get("messages", DEFAULT_MESSAGES)
        currency = config.get("currency_name", "spoons")
        levels = config.get("levels", DEFAULT_LEVELS)

        try:
            await asyncio.sleep(entry_duration)

            game.phase = "running"
            count = len(game.participants)
            level = self._get_level(count, levels)

            # --- Entry closed ---
            closed_msg = messages.get("entry_closed", DEFAULT_MESSAGES["entry_closed"])
            closed_msg = closed_msg.replace("$(level_name)", level["name"])
            try:
                await game.broadcaster.send_message(
                    sender=game.bot_id, message=closed_msg
                )
            except Exception:
                logger.exception("Failed to send entry-closed message")

            await asyncio.sleep(3)

            # --- Roll survival ---
            survival_chance = level["survival_chance"]
            for p in game.participants.values():
                p.survived = random.randint(1, 100) <= survival_chance

            survivors = [p for p in game.participants.values() if p.survived]
            dead = [p for p in game.participants.values() if not p.survived]
            survival_rate = len(survivors) / count if count > 0 else 0

            # --- Solo outcomes ---
            if count == 1:
                solo = list(game.participants.values())[0]
                if solo.survived:
                    payout = math.floor(solo.wager * level["multiplier"])
                    msg = messages.get("outcome_solo_win", DEFAULT_MESSAGES["outcome_solo_win"])
                    msg = (
                        msg.replace("$(user)", solo.display_name)
                        .replace("$(level_name)", level["name"])
                        .replace("$(payout)", str(payout))
                        .replace("$(currency)", currency)
                    )
                    await self._send_broadcast(game, msg)
                    await self._pay_winners(game, [solo], level, config)
                else:
                    msg = messages.get("outcome_solo_loss", DEFAULT_MESSAGES["outcome_solo_loss"])
                    msg = (
                        msg.replace("$(user)", solo.display_name)
                        .replace("$(level_name)", level["name"])
                    )
                    await self._send_broadcast(game, msg)
            else:
                # --- Group outcomes ---
                if survival_rate == 0:
                    outcome_key = "outcome_wipe"
                elif survival_rate < 0.5:
                    outcome_key = "outcome_few"
                elif survival_rate < 1.0:
                    outcome_key = "outcome_most"
                else:
                    outcome_key = "outcome_all"

                msg = messages.get(outcome_key, DEFAULT_MESSAGES[outcome_key])
                total_payout = sum(
                    math.floor(p.wager * level["multiplier"]) for p in survivors
                )
                msg = (
                    msg.replace("$(level_name)", level["name"])
                    .replace("$(total_payout)", str(total_payout))
                    .replace("$(currency)", currency)
                )
                await self._send_broadcast(game, msg)

                await asyncio.sleep(2)

                # --- Results ---
                if survivors:
                    await self._pay_winners(game, survivors, level, config)
                    winner_list = self._format_name_list(
                        [p.display_name for p in survivors]
                    )
                    results_msg = messages.get("results_winners", DEFAULT_MESSAGES["results_winners"])
                    results_msg = (
                        results_msg.replace("$(winner_list)", winner_list)
                        .replace("$(total_payout)", str(total_payout))
                        .replace("$(currency)", currency)
                    )
                    await self._send_broadcast(game, results_msg)

                if dead:
                    await asyncio.sleep(1)
                    loser_list = self._format_name_list(
                        [p.display_name for p in dead]
                    )
                    loser_msg = messages.get("results_losers", DEFAULT_MESSAGES["results_losers"])
                    loser_msg = loser_msg.replace("$(loser_list)", loser_list)
                    await self._send_broadcast(game, loser_msg)

        except asyncio.CancelledError:
            logger.info("Dungeon game cancelled for %s", game.broadcaster_id)
        except Exception:
            logger.exception("Dungeon game error for %s", game.broadcaster_id)
        finally:
            self._cooldowns[game.broadcaster_id] = time.monotonic()
            self._games.pop(game.broadcaster_id, None)

    async def _pay_winners(
        self,
        game: DungeonGame,
        survivors: list[DungeonParticipant],
        level: dict,
        config: dict,
    ) -> None:
        """Award payout to survivors via Synthfunc transact."""
        entries = []
        for p in survivors:
            payout = math.floor(p.wager * level["multiplier"])
            entries.append({
                "twitch_id": p.twitch_id,
                "amount": str(payout),
                "username": p.username,
                "display_name": p.display_name,
            })

        if entries:
            result = await transact_wallets(
                game.channel_name,
                entries,
                reason="dungeon_payout",
            )
            if result is None:
                logger.warning(
                    "Failed to pay dungeon winners for %s", game.broadcaster_id
                )

    async def _send_broadcast(self, game: DungeonGame, message: str) -> None:
        """Send a non-reply message to the channel."""
        try:
            await game.broadcaster.send_message(
                sender=game.bot_id, message=message
            )
        except Exception:
            logger.exception("Failed to send dungeon broadcast")

    @staticmethod
    def _get_level(player_count: int, levels: list[dict]) -> dict:
        """Return the highest level unlocked by the player count."""
        chosen = levels[0]
        for level in levels:
            if player_count >= level["min_players"]:
                chosen = level
        return chosen

    @staticmethod
    def _format_name_list(names: list[str], max_chars: int = 400) -> str:
        """Format a list of names, truncating if it would exceed Twitch's char limit."""
        if not names:
            return ""

        result = names[0]
        for i, name in enumerate(names[1:], start=2):
            candidate = f"{result}, {name}"
            remaining = len(names) - i
            suffix = f" and {remaining} more" if remaining > 0 else ""
            if len(candidate) + len(suffix) > max_chars:
                remaining_count = len(names) - (i - 1)
                return f"{result} and {remaining_count} more"
            result = candidate

        return result


register_skill(DungeonHandler())
