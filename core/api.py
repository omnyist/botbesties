from __future__ import annotations

import uuid

from ninja import Router
from ninja import Schema

# --- Command schemas and router ---

commands_router = Router(tags=["commands"])


class CommandSchema(Schema):
    id: uuid.UUID
    name: str
    type: str
    response: str
    config: dict
    enabled: bool
    use_count: int
    cooldown_seconds: int
    mod_only: bool


class CommandCreateSchema(Schema):
    name: str
    type: str = "text"
    response: str = ""
    config: dict = {}
    cooldown_seconds: int = 0
    mod_only: bool = False


@commands_router.get("/channels/{channel_id}/", response=list[CommandSchema])
async def list_commands(request, channel_id: uuid.UUID):
    """List all commands for a channel."""
    from core.models import Command

    commands = []
    async for cmd in Command.objects.filter(
        channel_id=channel_id, enabled=True
    ).order_by("name"):
        commands.append(cmd)
    return commands


# --- Counter schemas and router ---

counters_router = Router(tags=["counters"])


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
    label: str | None = None
    value: int | None = None


@counters_router.get("/channels/{channel_id}/", response=list[CounterSchema])
async def list_counters(request, channel_id: uuid.UUID):
    """List all counters for a channel."""
    from core.models import Counter

    counters = []
    async for counter in Counter.objects.filter(
        channel_id=channel_id
    ).order_by("name"):
        counters.append(counter)
    return counters


@counters_router.post("/channels/{channel_id}/", response=CounterSchema)
async def create_counter(request, channel_id: uuid.UUID, data: CounterCreateSchema):
    """Create a counter for a channel."""
    from asgiref.sync import sync_to_async

    from core.models import Counter

    counter = await sync_to_async(Counter.objects.create)(
        channel_id=channel_id,
        name=data.name,
        label=data.label,
        value=data.value,
    )
    return counter


@counters_router.patch("/{counter_id}/", response=CounterSchema)
async def update_counter(request, counter_id: uuid.UUID, data: CounterUpdateSchema):
    """Update a counter's value or label."""
    from asgiref.sync import sync_to_async

    from core.models import Counter

    counter = await sync_to_async(Counter.objects.get)(pk=counter_id)

    if data.label is not None:
        counter.label = data.label
    if data.value is not None:
        counter.value = data.value

    await sync_to_async(counter.save)()
    return counter


@counters_router.delete("/{counter_id}/")
async def delete_counter(request, counter_id: uuid.UUID):
    """Delete a counter."""
    from asgiref.sync import sync_to_async

    from core.models import Counter

    counter = await sync_to_async(Counter.objects.get)(pk=counter_id)
    await sync_to_async(counter.delete)()
    return {"success": True}


# --- Alias schemas and router ---

aliases_router = Router(tags=["aliases"])


class AliasSchema(Schema):
    id: uuid.UUID
    name: str
    target: str


class AliasCreateSchema(Schema):
    name: str
    target: str


@aliases_router.get("/channels/{channel_id}/", response=list[AliasSchema])
async def list_aliases(request, channel_id: uuid.UUID):
    """List all aliases for a channel."""
    from core.models import Alias

    aliases = []
    async for alias in Alias.objects.filter(
        channel_id=channel_id
    ).order_by("name"):
        aliases.append(alias)
    return aliases


@aliases_router.post("/channels/{channel_id}/", response=AliasSchema)
async def create_alias(request, channel_id: uuid.UUID, data: AliasCreateSchema):
    """Create an alias for a channel."""
    from asgiref.sync import sync_to_async

    from core.models import Alias

    alias = await sync_to_async(Alias.objects.create)(
        channel_id=channel_id,
        name=data.name,
        target=data.target,
    )
    return alias


@aliases_router.delete("/{alias_id}/")
async def delete_alias(request, alias_id: uuid.UUID):
    """Delete an alias."""
    from asgiref.sync import sync_to_async

    from core.models import Alias

    alias = await sync_to_async(Alias.objects.get)(pk=alias_id)
    await sync_to_async(alias.delete)()
    return {"success": True}


# --- Variable schema router ---

variables_router = Router(tags=["variables"])


@variables_router.get("/schema/")
def variable_schema(request):
    """Return the variable registry schema for autocomplete."""
    from bot.variables import create_registry

    registry = create_registry()
    return registry.schema()
