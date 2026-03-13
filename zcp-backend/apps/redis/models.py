import uuid
from django.db import models
from apps.organizations.models import Organization
from apps.projects.models import Project


class UpstashRedis(models.Model):
    STATUS_CHOICES = [
        ("provisioning", "Provisioning"),
        ("ready", "Ready"),
        ("error", "Error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="redis_instances"
    )
    zcp_project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="redis_instances",
        null=True, blank=True,
    )
    service_id = models.CharField(max_length=100, default="default")
    database_id = models.CharField(max_length=255, blank=True)
    endpoint = models.CharField(max_length=255, blank=True)
    port = models.IntegerField(default=6379)
    password = models.TextField(blank=True)
    rest_token = models.TextField(blank=True)
    tls = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="provisioning")
    metadata = models.JSONField(default=dict)
    temporal_workflow_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("organization", "service_id")]

    def __str__(self):
        return f"{self.organization.slug}/{self.service_id} ({self.status})"
