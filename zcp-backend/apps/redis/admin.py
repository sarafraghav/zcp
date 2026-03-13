from django.contrib import admin
from .models import UpstashRedis


@admin.register(UpstashRedis)
class UpstashRedisAdmin(admin.ModelAdmin):
    list_display = ("organization", "service_id", "status", "endpoint", "created_at")
    search_fields = ("organization__slug", "database_id", "endpoint")
    list_filter = ("status",)
    readonly_fields = (
        "id", "database_id", "endpoint", "port", "password",
        "rest_token", "temporal_workflow_id", "metadata", "created_at",
    )
