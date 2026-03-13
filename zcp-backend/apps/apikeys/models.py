import secrets
import uuid
from django.db import models
from django.conf import settings


def _generate_token() -> str:
    return f"zcp_{secrets.token_urlsafe(32)}"


class APIKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100, default="Default")
    token = models.CharField(max_length=100, unique=True, default=_generate_token)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} — {self.name}"

    def rotate(self) -> str:
        self.token = _generate_token()
        self.save(update_fields=["token"])
        return self.token
