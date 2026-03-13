from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ResourceAccessMapping


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "username", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "username")
    list_filter = ("is_staff", "is_active")


@admin.register(ResourceAccessMapping)
class ResourceAccessMappingAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    search_fields = ("user__email", "organization__slug")
    list_filter = ("role",)
    readonly_fields = ("created_at",)
