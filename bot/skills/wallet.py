"""!wallet — Check currency balance.

Usage:
    !wallet         — Check your own balance
    !wallet @kefka  — Check someone else's balance
"""

from __future__ import annotations

import logging

from bot.router import send_reply
from bot.skills import SkillHandler
from bot.skills import register_skill
from core.synthfunc import get_wallet

logger = logging.getLogger("bot")


class WalletHandler(SkillHandler):
    """!wallet — Check currency balance via Synthfunc wallets."""

    name = "wallet"

    async def handle(self, payload, args, skill, bot):
        chatter = payload.chatter
        chatter_name = chatter.display_name if chatter else "someone"

        if args:
            target = args.strip().lstrip("@")
            # Resolve target to Twitch ID
            try:
                users = await bot.fetch_users(names=[target])
            except Exception:
                logger.exception("Failed to fetch Twitch user: %s", target)
                await send_reply(
                    payload,
                    f"Could not find Twitch user {target}.",
                    bot_id=bot.bot_id,
                )
                return

            if not users:
                await send_reply(
                    payload,
                    f"Could not find Twitch user {target}.",
                    bot_id=bot.bot_id,
                )
                return

            user = users[0]
            twitch_id = str(user.id)
            display_name = user.display_name or target
            username = user.name or target
        else:
            twitch_id = str(chatter.id) if chatter else None
            display_name = chatter_name
            username = chatter.name if chatter else None

            if not twitch_id:
                await send_reply(
                    payload,
                    "Could not determine your Twitch ID.",
                    bot_id=bot.bot_id,
                )
                return

        wallet = await get_wallet(twitch_id, username=username)
        if not wallet:
            await send_reply(
                payload,
                f"@{display_name} doesn't have a wallet yet.",
                bot_id=bot.bot_id,
            )
            return

        balance = wallet.get("balance", "0")
        currency = wallet.get("currency_name", "points")

        # Format balance with commas
        try:
            bal_float = float(balance)
            if bal_float == int(bal_float):
                formatted = f"{int(bal_float):,}"
            else:
                formatted = f"{bal_float:,.1f}"
        except (ValueError, TypeError):
            formatted = balance

        await send_reply(
            payload,
            f"@{display_name} has {formatted} {currency}!",
            bot_id=bot.bot_id,
        )


register_skill(WalletHandler())
