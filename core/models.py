from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from encrypted_fields import EncryptedTextField


class Bot(models.Model):
    """Bot identity (e.g., Elsydeon, WorldFriendshipBot).

    Each bot connects to Twitch with its own credentials and speaks
    in one or more channels.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    twitch_user_id = models.CharField(max_length=50, unique=True)
    twitch_username = models.CharField(max_length=100)

    access_token = EncryptedTextField(null=True, blank=True)
    refresh_token = EncryptedTextField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

    @property
    def is_connected(self) -> bool:
        return bool(self.access_token)


class Channel(models.Model):
    """A channel where a bot is active.

    Stores both the channel identity and the channel owner's OAuth tokens,
    which are needed for moderation actions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="channels")
    twitch_channel_id = models.CharField(max_length=50)
    twitch_channel_name = models.CharField(max_length=100)

    owner_access_token = EncryptedTextField(null=True, blank=True)
    owner_refresh_token = EncryptedTextField(null=True, blank=True)
    owner_token_expires_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ["bot", "twitch_channel_id"]

    def __str__(self):
        return f"{self.bot.name} in #{self.twitch_channel_name}"

    @property
    def is_owner_connected(self) -> bool:
        return bool(self.owner_access_token)


class Command(models.Model):
    """A command triggered by !name in chat.

    The type determines how the response is chosen and what side effects happen:
    - text: Static response template from `response` field
    - lottery: Roll odds, pick success or failure from `config`
    - random_list: Random pick from `config["responses"]`
    - counter: Auto-increment a named counter, then respond with `response` template

    Response text supports variables like $(user), $(channel), $(uses).
    """

    class Type(models.TextChoices):
        TEXT = "text", "Text"
        LOTTERY = "lottery", "Lottery"
        RANDOM_LIST = "random_list", "Random List"
        COUNTER = "counter", "Counter"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="commands"
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.TEXT)
    response = models.TextField(blank=True, default="")
    config = models.JSONField(default=dict, blank=True)

    enabled = models.BooleanField(default=True)
    use_count = models.PositiveIntegerField(default=0)
    cooldown_seconds = models.PositiveIntegerField(default=0)
    user_cooldown_seconds = models.PositiveIntegerField(default=0)
    mod_only = models.BooleanField(default=False)

    created_by = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["channel", "name"]
        ordering = ["name"]

    def __str__(self):
        return f"!{self.name} in #{self.channel.twitch_channel_name}"


class Skill(models.Model):
    """A Python-implemented command toggled per channel.

    The actual logic lives in bot/skills/ as Python handler classes.
    This model controls whether the skill is enabled for a channel
    and provides per-channel configuration via the config JSON field.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="skills"
    )
    name = models.CharField(max_length=50)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ["channel", "name"]
        ordering = ["name"]

    def __str__(self):
        status = "enabled" if self.enabled else "disabled"
        return f"!{self.name} ({status}) in #{self.channel.twitch_channel_name}"


class Counter(models.Model):
    """A named counter per channel (death count, scare count, etc.).

    Stored as a dedicated model (not Skill.config JSON) so we can use
    Django F() expressions for atomic increments and provide direct
    admin editing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="counters"
    )
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=100, blank=True, default="")
    value = models.IntegerField(default=0)

    class Meta:
        unique_together = ["channel", "name"]
        ordering = ["name"]

    def __str__(self):
        display = self.label or self.name.title()
        return f"{display}: {self.value} in #{self.channel.twitch_channel_name}"


class Alias(models.Model):
    """A type-agnostic command alias per channel.

    Resolved early in the message pipeline — rewrites the trigger to
    the target text before routing. Works for both text commands and
    skills transparently.

    Example: name="ct", target="count death" rewrites !ct → !count death.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="aliases"
    )
    name = models.CharField(max_length=100)
    target = models.CharField(max_length=200)

    class Meta:
        unique_together = ["channel", "name"]
        ordering = ["name"]

    def __str__(self):
        return f"!{self.name} → !{self.target} in #{self.channel.twitch_channel_name}"
