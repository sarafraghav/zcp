from django.contrib import admin
from apps.projects.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "created_at")
    search_fields = ("name", "organization__slug")
    list_filter = ("created_at",)
