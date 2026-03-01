from __future__ import annotations

from django.contrib import admin
from django.urls import include
from django.urls import path
from ninja import NinjaAPI

from core.api import router as core_router

api = NinjaAPI(urls_namespace="main")
api.add_router("/commands/", core_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("setup/", include("core.auth_urls")),
]
