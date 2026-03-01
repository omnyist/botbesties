from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass

from asgiref.sync import sync_to_async

logger = logging.getLogger("bot")

VARIABLE_PATTERN = re.compile(r"\$\((\w+)(?:\.(\w+))?(?:\s+([^)]+))?\)")


@dataclass
class VariableContext:
    """Context passed to every variable handler during resolution."""

    user: str
    target: str
    channel_name: str
    broadcaster_id: str
    command_name: str
    use_count: int
    raw_args: str


@dataclass
class VariableDescriptor:
    """Describes a single variable form for schema generation."""

    namespace: str
    property: str | None
    args_hint: str | None
    description: str
    example: str


class VariableHandler:
    """Base class for variable handlers.

    Each handler owns a namespace (e.g., "user", "count", "random")
    and resolves variables within that namespace.
    """

    namespace: str = ""

    async def resolve(
        self,
        prop: str | None,
        args: str | None,
        context: VariableContext,
    ) -> str:
        raise NotImplementedError

    def describe(self) -> list[VariableDescriptor]:
        raise NotImplementedError


class UserHandler(VariableHandler):
    """$(user) — chatter display name."""

    namespace = "user"

    async def resolve(self, prop, args, context):
        return context.user

    def describe(self):
        return [
            VariableDescriptor(
                namespace="user",
                property=None,
                args_hint=None,
                description="Display name of the chatter who triggered the command.",
                example="$(user)",
            ),
        ]


class TargetHandler(VariableHandler):
    """$(target) — first argument with @ stripped, falls back to $(user)."""

    namespace = "target"

    async def resolve(self, prop, args, context):
        return context.target

    def describe(self):
        return [
            VariableDescriptor(
                namespace="target",
                property=None,
                args_hint=None,
                description=(
                    "First argument after the command with @ stripped. "
                    "Falls back to the chatter name if no argument given."
                ),
                example="$(target)",
            ),
        ]


class ChannelHandler(VariableHandler):
    """$(channel) — broadcaster channel name."""

    namespace = "channel"

    async def resolve(self, prop, args, context):
        return context.channel_name

    def describe(self):
        return [
            VariableDescriptor(
                namespace="channel",
                property=None,
                args_hint=None,
                description="Name of the current channel.",
                example="$(channel)",
            ),
        ]


class UsesHandler(VariableHandler):
    """$(uses) — how many times this text command has been used."""

    namespace = "uses"

    async def resolve(self, prop, args, context):
        return str(context.use_count)

    def describe(self):
        return [
            VariableDescriptor(
                namespace="uses",
                property=None,
                args_hint=None,
                description="How many times this command has been used.",
                example="$(uses)",
            ),
        ]


class CountHandler(VariableHandler):
    """$(count.get <name>) — read a named counter value.

    $(count.label <name>) — read a counter's display label.
    """

    namespace = "count"

    async def resolve(self, prop, args, context):
        if not prop or not args:
            return "$(count)"

        counter_name = args.strip()

        from core.models import Counter

        try:
            counter = await sync_to_async(Counter.objects.get)(
                channel__twitch_channel_id=context.broadcaster_id,
                channel__is_active=True,
                name=counter_name,
            )
        except Counter.DoesNotExist:
            return "0" if prop == "get" else counter_name.title()

        if prop == "get":
            return str(counter.value)
        elif prop == "label":
            return counter.label or counter.name.title()

        return "$(count)"

    def describe(self):
        return [
            VariableDescriptor(
                namespace="count",
                property="get",
                args_hint="<name>",
                description="Current value of a named counter.",
                example="$(count.get death)",
            ),
            VariableDescriptor(
                namespace="count",
                property="label",
                args_hint="<name>",
                description="Display label of a named counter.",
                example="$(count.label death)",
            ),
        ]


class RandomHandler(VariableHandler):
    """$(random.range N-M) — random integer in range.

    $(random.pick a,b,c) — random choice from comma-separated list.
    """

    namespace = "random"

    async def resolve(self, prop, args, context):
        if not prop or not args:
            return "$(random)"

        if prop == "range":
            try:
                parts = args.split("-")
                low, high = int(parts[0].strip()), int(parts[1].strip())
                return str(random.randint(low, high))
            except (ValueError, IndexError):
                return "$(random.range)"
        elif prop == "pick":
            choices = [c.strip() for c in args.split(",") if c.strip()]
            if choices:
                return random.choice(choices)
            return "$(random.pick)"

        return "$(random)"

    def describe(self):
        return [
            VariableDescriptor(
                namespace="random",
                property="range",
                args_hint="N-M",
                description="Random integer between N and M (inclusive).",
                example="$(random.range 1-100)",
            ),
            VariableDescriptor(
                namespace="random",
                property="pick",
                args_hint="a,b,c",
                description="Random choice from a comma-separated list.",
                example="$(random.pick heads,tails)",
            ),
        ]


class QueryHandler(VariableHandler):
    """$(query) — full raw argument string after the command name."""

    namespace = "query"

    async def resolve(self, prop, args, context):
        return context.raw_args

    def describe(self):
        return [
            VariableDescriptor(
                namespace="query",
                property=None,
                args_hint=None,
                description="Full argument string after the command name.",
                example="$(query)",
            ),
        ]


class IndexHandler(VariableHandler):
    """$(1), $(2), etc. — positional arguments.

    This handler is special: it handles numeric namespaces.
    The registry dispatches any namespace that is a digit to this handler.
    """

    namespace = "_index"

    async def resolve(self, prop, args, context):
        return ""

    async def resolve_index(self, index: int, context: VariableContext) -> str:
        """Resolve a positional argument by 1-based index."""
        parts = context.raw_args.split() if context.raw_args else []
        if 1 <= index <= len(parts):
            return parts[index - 1]
        return ""

    def describe(self):
        return [
            VariableDescriptor(
                namespace="1",
                property=None,
                args_hint=None,
                description="First word after the command name.",
                example="$(1)",
            ),
            VariableDescriptor(
                namespace="2",
                property=None,
                args_hint=None,
                description="Second word after the command name.",
                example="$(2)",
            ),
            VariableDescriptor(
                namespace="N",
                property=None,
                args_hint=None,
                description="Nth positional argument (1-based).",
                example="$(3)",
            ),
        ]


class VariableRegistry:
    """Orchestrates variable resolution across all registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, VariableHandler] = {}
        self._index_handler: IndexHandler | None = None

    def register(self, handler: VariableHandler) -> None:
        if isinstance(handler, IndexHandler):
            self._index_handler = handler
        else:
            self._handlers[handler.namespace] = handler

    async def process(self, template: str, context: VariableContext) -> str:
        """Replace all $(namespace.property args) variables in template."""
        matches = list(VARIABLE_PATTERN.finditer(template))
        if not matches:
            return template

        # Collect all resolutions concurrently
        tasks = []
        for match in matches:
            namespace = match.group(1).lower()
            prop = match.group(2)
            args = match.group(3)

            if namespace.isdigit() and self._index_handler:
                tasks.append(
                    self._index_handler.resolve_index(int(namespace), context)
                )
            elif namespace in self._handlers:
                tasks.append(
                    self._handlers[namespace].resolve(prop, args, context)
                )
            else:
                # Unknown variable — leave it as-is

                async def _passthrough(text=match.group(0)):
                    return text

                tasks.append(_passthrough())

        results = await asyncio.gather(*tasks)

        # Replace matches in reverse order to preserve positions
        result = template
        for match, replacement in zip(reversed(matches), reversed(results)):
            result = result[: match.start()] + replacement + result[match.end() :]

        return result

    def schema(self) -> list[dict]:
        """Generate the variable schema for all handlers."""
        descriptors = []
        for handler in self._handlers.values():
            for desc in handler.describe():
                descriptors.append(
                    {
                        "namespace": desc.namespace,
                        "property": desc.property,
                        "args_hint": desc.args_hint,
                        "description": desc.description,
                        "example": desc.example,
                    }
                )
        if self._index_handler:
            for desc in self._index_handler.describe():
                descriptors.append(
                    {
                        "namespace": desc.namespace,
                        "property": desc.property,
                        "args_hint": desc.args_hint,
                        "description": desc.description,
                        "example": desc.example,
                    }
                )
        return descriptors


def create_registry() -> VariableRegistry:
    """Create and populate the default variable registry."""
    registry = VariableRegistry()
    registry.register(UserHandler())
    registry.register(TargetHandler())
    registry.register(ChannelHandler())
    registry.register(UsesHandler())
    registry.register(CountHandler())
    registry.register(RandomHandler())
    registry.register(QueryHandler())
    registry.register(IndexHandler())
    return registry
