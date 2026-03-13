from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class APIKeyAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith(f"{self.keyword} "):
            return None
        token = auth[len(self.keyword) + 1:].strip()
        if not token.startswith("zcp_"):
            return None

        from apps.apikeys.models import APIKey
        try:
            key = APIKey.objects.select_related("user").get(token=token, is_active=True)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid or inactive API key.")

        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return (key.user, key)

    def authenticate_header(self, request):
        return self.keyword
