from __future__ import annotations

BOT_SCOPES = [
    "chat:read",
    "chat:edit",
    "user:bot",
    "user:read:chat",
    "user:write:chat",
]

CHANNEL_SCOPES = [
    # Moderation
    "channel:bot",
    "channel:moderate",
    "channel:read:subscriptions",
    "moderator:manage:banned_users",
    "moderator:manage:chat_messages",
    "moderator:read:chatters",
    "moderator:read:followers",
    # EventSub (used by Synthfunc for event ingestion)
    "bits:read",
    "channel:read:ads",
    "channel:read:charity",
    "channel:read:goals",
    "channel:read:hype_train",
    "channel:read:polls",
    "channel:read:predictions",
    "channel:manage:redemptions",
    "channel:read:redemptions",
    "channel:read:vips",
    "moderator:read:shoutouts",
    "user:read:chat",
]
