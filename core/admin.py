from __future__ import annotations

from django.contrib import admin

from .models import Alias
from .models import Bot
from .models import Channel
from .models import Command
from .models import Counter
from .models import Skill


class ChannelInline(admin.TabularInline):
    model = Channel
    extra = 0
    fields = [
        "twitch_channel_name",
        "twitch_channel_id",
        "is_active",
        "is_owner_connected",
    ]
    readonly_fields = ["is_owner_connected"]


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("name", "twitch_username", "twitch_user_id", "is_connected")
    search_fields = ("name", "twitch_username")
    readonly_fields = ("created_at",)
    inlines = [ChannelInline]


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = (
        "twitch_channel_name",
        "bot",
        "is_active",
        "is_owner_connected",
        "joined_at",
    )
    list_filter = ("bot", "is_active")
    search_fields = ("twitch_channel_name",)
    readonly_fields = ("joined_at",)


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "channel",
        "enabled",
        "mod_only",
        "use_count",
        "created_by",
    )
    list_filter = ("channel", "type", "enabled", "mod_only")
    search_fields = ("name", "response")
    readonly_fields = ("use_count", "created_at", "updated_at")
    ordering = ["channel", "name"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "channel", "enabled")
    list_filter = ("channel", "enabled")
    search_fields = ("name",)
    ordering = ["channel", "name"]


@admin.register(Counter)
class CounterAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "channel", "value")
    list_filter = ("channel",)
    search_fields = ("name", "label")
    ordering = ["channel", "name"]


@admin.register(Alias)
class AliasAdmin(admin.ModelAdmin):
    list_display = ("name", "target", "channel")
    list_filter = ("channel",)
    search_fields = ("name", "target")
    ordering = ["channel", "name"]
