from django.contrib import admin
from .models import NeonDatabase


@admin.register(NeonDatabase)
class NeonDatabaseAdmin(admin.ModelAdmin):
    list_display = ("organization", "service_id", "status", "project_id", "database_name", "created_at")
    search_fields = ("organization__slug", "project_id", "database_name")
    list_filter = ("status",)
    readonly_fields = ("id", "service_id", "project_id", "database_name", "connection_string", "temporal_workflow_id", "metadata", "created_at")
