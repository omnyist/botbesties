from __future__ import annotations

from django.db import models
from django.utils import timezone
from encrypted_fields import EncryptedTextField


class Bot(models.Model):
    """Bot identity (e.g., Elsydeon, WorldFriendshipBot).

    Each bot connects to Twitch with its own credentials and speaks
    in one or more channels.
    """

    name = models.CharField(max_length=100)
    twitch_user_id = models.CharField(max_length=50, unique=True)
    twitch_username = models.CharField(max_length=100)

    access_token = EncryptedTextField(blank=True, default="")
    refresh_token = EncryptedTextField(blank=True, default="")
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

    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="channels")
    twitch_channel_id = models.CharField(max_length=50)
    twitch_channel_name = models.CharField(max_length=100)

    owner_access_token = EncryptedTextField(blank=True, default="")
    owner_refresh_token = EncryptedTextField(blank=True, default="")
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
    """A text command defined via chat (!addcom) or admin.

    Response text supports variables like $(user), $(channel), $(count).
    """

    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="commands"
    )
    name = models.CharField(max_length=100)
    response = models.TextField()

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


class CodedCommand(models.Model):
    """A Python-implemented command toggled per channel.

    The actual logic lives in bot/components/ as Python code.
    This model controls whether the command is enabled for a channel
    and provides per-channel configuration via the config JSON field.
    """

    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="coded_commands"
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
