from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from asgiref.sync import sync_to_async
from django.db import IntegrityError
from ninja import Router
from ninja import Schema
from ninja.errors import HttpError

from .models import Channel
from .models import Command
from .models import TwitchProfile

v1_router = Router()

VALID_COMMAND_NAME = re.compile(r"^[a-zA-Z0-9_]+$")


# --- Auth helpers ---


def _require_auth(request):
    """Check that the request is authenticated, raise 401 if not."""
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    return request.user


async def _get_profile(user) -> TwitchProfile:
    """Get the TwitchProfile for the given user."""
    try:
        return await sync_to_async(
            TwitchProfile.objects.select_related("user").get
        )(user=user)
    except TwitchProfile.DoesNotExist:
        raise HttpError(403, "No Twitch profile linked")


async def _get_user_channel(request, channel_id: uuid.UUID) -> tuple:
    """Verify the authenticated user owns this channel, or raise 403.

    Returns (channel, profile) to avoid redundant profile lookups.
    """
    user = _require_auth(request)
    profile = await _get_profile(user)

    try:
        channel = await sync_to_async(
            Channel.objects.select_related("bot").get
        )(pk=channel_id, is_active=True)
    except Channel.DoesNotExist:
        raise HttpError(404, "Channel not found")

    if channel.twitch_channel_id != profile.twitch_id:
        raise HttpError(403, "Not authorized for this channel")

    return channel, profile


async def _get_user_command(request, command_id: uuid.UUID) -> Command:
    """Verify the authenticated user owns this command's channel, or raise."""
    user = _require_auth(request)
    profile = await _get_profile(user)

    try:
        cmd = await sync_to_async(
            Command.objects.select_related("channel").get
        )(pk=command_id)
    except Command.DoesNotExist:
        raise HttpError(404, "Command not found")

    if cmd.channel.twitch_channel_id != profile.twitch_id:
        raise HttpError(403, "Not authorized for this channel")

    return cmd


# --- Me ---


class ChannelBriefSchema(Schema):
    id: uuid.UUID
    name: str
    bot_name: str


class MeSchema(Schema):
    twitch_id: str
    twitch_username: str
    twitch_display_name: str
    twitch_avatar: str
    channels: list[ChannelBriefSchema]


@v1_router.get("/me", response=MeSchema)
async def me(request):
    """Return the authenticated user's info and their channels."""
    user = _require_auth(request)
    profile = await _get_profile(user)

    channels = []
    async for channel in Channel.objects.filter(
        twitch_channel_id=profile.twitch_id, is_active=True
    ).select_related("bot"):
        channels.append(
            ChannelBriefSchema(
                id=channel.id,
                name=channel.twitch_channel_name,
                bot_name=channel.bot.name,
            )
        )

    return MeSchema(
        twitch_id=profile.twitch_id,
        twitch_username=profile.twitch_username,
        twitch_display_name=profile.twitch_display_name,
        twitch_avatar=profile.twitch_avatar,
        channels=channels,
    )


# --- Channels ---


@v1_router.get("/channels/", response=list[ChannelBriefSchema])
async def list_channels(request):
    """List channels the authenticated user owns."""
    user = _require_auth(request)
    profile = await _get_profile(user)

    channels = []
    async for channel in Channel.objects.filter(
        twitch_channel_id=profile.twitch_id, is_active=True
    ).select_related("bot"):
        channels.append(
            ChannelBriefSchema(
                id=channel.id,
                name=channel.twitch_channel_name,
                bot_name=channel.bot.name,
            )
        )

    return channels


# --- Commands ---


class CommandSchema(Schema):
    id: uuid.UUID
    name: str
    type: str
    response: str
    config: dict
    enabled: bool
    use_count: int
    cooldown_seconds: int
    user_cooldown_seconds: int
    mod_only: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class CommandCreateSchema(Schema):
    name: str
    type: Literal["text", "lottery", "random_list", "counter"] = "text"
    response: str = ""
    config: dict = {}
    cooldown_seconds: int = 0
    user_cooldown_seconds: int = 0
    mod_only: bool = False


class CommandUpdateSchema(Schema):
    name: str | None = None
    type: Literal["text", "lottery", "random_list", "counter"] | None = None
    response: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    cooldown_seconds: int | None = None
    user_cooldown_seconds: int | None = None
    mod_only: bool | None = None


@v1_router.get(
    "/commands/channels/{channel_id}/", response=list[CommandSchema]
)
async def list_commands(request, channel_id: uuid.UUID):
    """List all commands for a channel (including disabled)."""
    channel, _ = await _get_user_channel(request, channel_id)

    commands = []
    async for cmd in Command.objects.filter(channel=channel).order_by("name"):
        commands.append(cmd)
    return commands


@v1_router.post("/commands/channels/{channel_id}/", response=CommandSchema)
async def create_command(
    request, channel_id: uuid.UUID, data: CommandCreateSchema
):
    """Create a command for a channel."""
    if not data.name or not VALID_COMMAND_NAME.match(data.name):
        raise HttpError(
            422, "Command name must be non-empty and contain only letters, numbers, and underscores."
        )

    channel, profile = await _get_user_channel(request, channel_id)

    try:
        cmd = await sync_to_async(Command.objects.create)(
            channel=channel,
            name=data.name,
            type=data.type,
            response=data.response,
            config=data.config,
            cooldown_seconds=data.cooldown_seconds,
            user_cooldown_seconds=data.user_cooldown_seconds,
            mod_only=data.mod_only,
            created_by=profile.twitch_display_name,
        )
    except IntegrityError:
        raise HttpError(409, f"Command '!{data.name}' already exists in this channel.")

    return cmd


@v1_router.get("/commands/{command_id}/", response=CommandSchema)
async def get_command(request, command_id: uuid.UUID):
    """Get a single command by ID."""
    return await _get_user_command(request, command_id)


@v1_router.patch("/commands/{command_id}/", response=CommandSchema)
async def update_command(
    request, command_id: uuid.UUID, data: CommandUpdateSchema
):
    """Update a command."""
    cmd = await _get_user_command(request, command_id)

    update_fields = []
    for field_name in [
        "name", "type", "response", "config", "enabled",
        "cooldown_seconds", "user_cooldown_seconds", "mod_only",
    ]:
        value = getattr(data, field_name)
        if value is not None:
            setattr(cmd, field_name, value)
            update_fields.append(field_name)

    if update_fields:
        await sync_to_async(cmd.save)(update_fields=update_fields)

    return cmd


@v1_router.delete("/commands/{command_id}/")
async def delete_command(request, command_id: uuid.UUID):
    """Delete a command."""
    cmd = await _get_user_command(request, command_id)
    await sync_to_async(cmd.delete)()
    return {"success": True}


# --- Variables ---


@v1_router.get("/variables/schema/")
def variable_schema(request):
    """Return the variable registry schema for autocomplete."""
    _require_auth(request)

    from bot.variables import create_registry

    registry = create_registry()
    return registry.schema()
