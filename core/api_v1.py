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

from .models import Alias
from .models import Channel
from .models import Command
from .models import Counter
from .models import TwitchProfile

v1_router = Router()

VALID_COMMAND_NAME = re.compile(r"^[a-zA-Z0-9_]+$")


# --- Auth helpers ---


async def _require_auth(request):
    """Check that the request is authenticated, raise 401 if not."""
    user = await sync_to_async(lambda: request.user)()
    is_auth = await sync_to_async(lambda: user.is_authenticated)()
    if not is_auth:
        raise HttpError(401, "Not authenticated")
    return user


async def _get_profile(user) -> TwitchProfile:
    """Get the TwitchProfile for the given user."""
    try:
        return await sync_to_async(
            TwitchProfile.objects.select_related("user").get
        )(user=user)
    except TwitchProfile.DoesNotExist:
        raise HttpError(403, "No Twitch profile linked")


async def _get_user_channel(request, channel_slug: str) -> tuple:
    """Verify the authenticated user owns this channel, or raise 403.

    Returns (channel, profile) to avoid redundant profile lookups.
    """
    user = await _require_auth(request)
    profile = await _get_profile(user)

    channel = await sync_to_async(
        Channel.objects.filter(
            twitch_channel_name=channel_slug,
            twitch_channel_id=profile.twitch_id,
            is_active=True,
        )
        .select_related("bot")
        .first
    )()

    if not channel:
        raise HttpError(404, "Channel not found")

    return channel, profile


async def _get_user_command(request, command_id: uuid.UUID) -> Command:
    """Verify the authenticated user owns this command's channel, or raise."""
    user = await _require_auth(request)
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


async def _get_user_counter(request, counter_id: uuid.UUID) -> Counter:
    """Verify the authenticated user owns this counter's channel, or raise."""
    user = await _require_auth(request)
    profile = await _get_profile(user)

    try:
        counter = await sync_to_async(
            Counter.objects.select_related("channel").get
        )(pk=counter_id)
    except Counter.DoesNotExist:
        raise HttpError(404, "Counter not found")

    if counter.channel.twitch_channel_id != profile.twitch_id:
        raise HttpError(403, "Not authorized for this channel")

    return counter


async def _get_user_alias(request, alias_id: uuid.UUID) -> Alias:
    """Verify the authenticated user owns this alias's channel, or raise."""
    user = await _require_auth(request)
    profile = await _get_profile(user)

    try:
        alias = await sync_to_async(
            Alias.objects.select_related("channel").get
        )(pk=alias_id)
    except Alias.DoesNotExist:
        raise HttpError(404, "Alias not found")

    if alias.channel.twitch_channel_id != profile.twitch_id:
        raise HttpError(403, "Not authorized for this channel")

    return alias


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
    user = await _require_auth(request)
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
    user = await _require_auth(request)
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
    "/commands/channels/{channel_slug}/", response=list[CommandSchema]
)
async def list_commands(request, channel_slug: str):
    """List all commands for a channel (including disabled)."""
    channel, _ = await _get_user_channel(request, channel_slug)

    commands = []
    async for cmd in Command.objects.filter(channel=channel).order_by("name"):
        commands.append(cmd)
    return commands


@v1_router.post("/commands/channels/{channel_slug}/", response=CommandSchema)
async def create_command(
    request, channel_slug: str, data: CommandCreateSchema
):
    """Create a command for a channel."""
    if not data.name or not VALID_COMMAND_NAME.match(data.name):
        raise HttpError(
            422, "Command name must be non-empty and contain only letters, numbers, and underscores."
        )

    channel, profile = await _get_user_channel(request, channel_slug)

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
async def variable_schema(request):
    """Return the variable registry schema for autocomplete."""
    await _require_auth(request)

    from bot.variables import create_registry

    registry = create_registry()
    return registry.schema()


# --- Counters ---


class CounterSchema(Schema):
    id: uuid.UUID
    name: str
    label: str
    value: int


class CounterCreateSchema(Schema):
    name: str
    label: str = ""
    value: int = 0


class CounterUpdateSchema(Schema):
    name: str | None = None
    label: str | None = None
    value: int | None = None


@v1_router.get(
    "/counters/channels/{channel_slug}/", response=list[CounterSchema]
)
async def list_counters(request, channel_slug: str):
    """List all counters for a channel."""
    channel, _ = await _get_user_channel(request, channel_slug)

    counters = []
    async for counter in Counter.objects.filter(channel=channel).order_by("name"):
        counters.append(counter)
    return counters


@v1_router.post("/counters/channels/{channel_slug}/", response=CounterSchema)
async def create_counter(
    request, channel_slug: str, data: CounterCreateSchema
):
    """Create a counter for a channel."""
    if not data.name or not VALID_COMMAND_NAME.match(data.name):
        raise HttpError(
            422, "Counter name must be non-empty and contain only letters, numbers, and underscores."
        )

    channel, _ = await _get_user_channel(request, channel_slug)

    try:
        counter = await sync_to_async(Counter.objects.create)(
            channel=channel,
            name=data.name,
            label=data.label,
            value=data.value,
        )
    except IntegrityError:
        raise HttpError(409, f"Counter '{data.name}' already exists in this channel.")

    return counter


@v1_router.patch("/counters/{counter_id}/", response=CounterSchema)
async def update_counter(
    request, counter_id: uuid.UUID, data: CounterUpdateSchema
):
    """Update a counter."""
    counter = await _get_user_counter(request, counter_id)

    update_fields = []
    for field_name in ["name", "label", "value"]:
        value = getattr(data, field_name)
        if value is not None:
            setattr(counter, field_name, value)
            update_fields.append(field_name)

    if update_fields:
        await sync_to_async(counter.save)(update_fields=update_fields)

    return counter


@v1_router.delete("/counters/{counter_id}/")
async def delete_counter(request, counter_id: uuid.UUID):
    """Delete a counter."""
    counter = await _get_user_counter(request, counter_id)
    await sync_to_async(counter.delete)()
    return {"success": True}


# --- Aliases ---


class AliasSchema(Schema):
    id: uuid.UUID
    name: str
    target: str


class AliasCreateSchema(Schema):
    name: str
    target: str


class AliasUpdateSchema(Schema):
    name: str | None = None
    target: str | None = None


@v1_router.get(
    "/aliases/channels/{channel_slug}/", response=list[AliasSchema]
)
async def list_aliases(request, channel_slug: str):
    """List all aliases for a channel."""
    channel, _ = await _get_user_channel(request, channel_slug)

    aliases = []
    async for alias in Alias.objects.filter(channel=channel).order_by("name"):
        aliases.append(alias)
    return aliases


@v1_router.post("/aliases/channels/{channel_slug}/", response=AliasSchema)
async def create_alias(
    request, channel_slug: str, data: AliasCreateSchema
):
    """Create an alias for a channel."""
    if not data.name or not VALID_COMMAND_NAME.match(data.name):
        raise HttpError(
            422, "Alias name must be non-empty and contain only letters, numbers, and underscores."
        )

    channel, _ = await _get_user_channel(request, channel_slug)

    try:
        alias = await sync_to_async(Alias.objects.create)(
            channel=channel,
            name=data.name,
            target=data.target,
        )
    except IntegrityError:
        raise HttpError(409, f"Alias '!{data.name}' already exists in this channel.")

    return alias


@v1_router.patch("/aliases/{alias_id}/", response=AliasSchema)
async def update_alias(
    request, alias_id: uuid.UUID, data: AliasUpdateSchema
):
    """Update an alias."""
    alias = await _get_user_alias(request, alias_id)

    update_fields = []
    for field_name in ["name", "target"]:
        value = getattr(data, field_name)
        if value is not None:
            setattr(alias, field_name, value)
            update_fields.append(field_name)

    if update_fields:
        await sync_to_async(alias.save)(update_fields=update_fields)

    return alias


@v1_router.delete("/aliases/{alias_id}/")
async def delete_alias(request, alias_id: uuid.UUID):
    """Delete an alias."""
    alias = await _get_user_alias(request, alias_id)
    await sync_to_async(alias.delete)()
    return {"success": True}
