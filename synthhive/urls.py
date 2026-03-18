from __future__ import annotations

import re

from django.conf import settings
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.urls import re_path
from django.views.static import serve
from ninja import NinjaAPI

from core.api import aliases_router
from core.api import commands_router
from core.api import counters_router
from core.api import variables_router
from core.api_v1 import v1_router

api = NinjaAPI(urls_namespace="main")
api.add_router("/commands/", commands_router)
api.add_router("/counters/", counters_router)
api.add_router("/aliases/", aliases_router)
api.add_router("/variables/", variables_router)
api.add_router("/v1/", v1_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("auth/", include("core.dashboard_auth_urls")),
    path("setup/", include("core.auth_urls")),
]

# Serve static files via Django's URL routing.
# WhiteNoise middleware doesn't support ASGI (Daphne), so we serve
# static files through Django's built-in view instead.
urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % re.escape(settings.STATIC_URL.lstrip("/")),
        serve,
        {"document_root": settings.STATIC_ROOT},
    ),
]
