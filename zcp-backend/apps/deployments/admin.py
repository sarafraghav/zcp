from django.contrib import admin
from .models import DeployedApp


@admin.register(DeployedApp)
class DeployedAppAdmin(admin.ModelAdmin):
    list_display = ["app_name", "organization", "status", "temporal_workflow_id", "created_at"]
    list_filter = ["status"]
    search_fields = ["organization__slug", "app_name", "temporal_workflow_id"]
    readonly_fields = ["id", "created_at"]
