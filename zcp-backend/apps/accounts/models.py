from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.organizations.models import Organization


class User(AbstractUser):
    pass


class ResourceAccessMapping(models.Model):
    ROLE_CHOICES = [("owner", "Owner"), ("member", "Member")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="access_mappings")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="access_mappings")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="owner")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "organization")

    def __str__(self):
        return f"{self.user.email} → {self.organization.slug} ({self.role})"
