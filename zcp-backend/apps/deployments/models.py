import uuid
from django.db import models
from apps.organizations.models import Organization
from apps.projects.models import Project


class DeployedApp(models.Model):
    STATUS_CHOICES = [
        ("deploying", "Deploying"),
        ("ready", "Ready"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="deployed_apps"
    )
    zcp_project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="deployed_apps",
        null=True, blank=True,
    )
    app_name = models.CharField(max_length=255, blank=True)
    service_urls = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="deploying")
    metadata = models.JSONField(default=dict)
    temporal_workflow_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.app_name} ({self.organization.slug})"
