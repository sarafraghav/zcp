from django.contrib import admin
from .models import APIKey


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "is_active", "created_at", "last_used_at")
    search_fields = ("user__email", "name")
    list_filter = ("is_active",)
    readonly_fields = ("id", "token", "created_at", "last_used_at")
