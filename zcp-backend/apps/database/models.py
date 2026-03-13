import uuid
from django.db import models
from apps.organizations.models import Organization
from apps.projects.models import Project


class NeonDatabase(models.Model):
    STATUS_CHOICES = [
        ("provisioning", "Provisioning"),
        ("ready", "Ready"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="databases"
    )
    zcp_project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="databases",
        null=True, blank=True,
    )
    service_id = models.CharField(max_length=100, default="default")
    project_id = models.CharField(max_length=255, blank=True)
    database_name = models.CharField(max_length=255, blank=True)
    connection_string = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="provisioning")
    metadata = models.JSONField(default=dict)
    temporal_workflow_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("organization", "service_id")]

    def __str__(self):
        return f"{self.organization.slug}/{self.service_id} ({self.status})"
