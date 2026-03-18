from __future__ import annotations

from django.urls import path

from . import dashboard_auth

urlpatterns = [
    path("twitch/login/", dashboard_auth.twitch_login, name="dashboard_twitch_login"),
    path(
        "twitch/callback/",
        dashboard_auth.twitch_callback,
        name="dashboard_twitch_callback",
    ),
    path("logout/", dashboard_auth.dashboard_logout, name="dashboard_logout"),
]
