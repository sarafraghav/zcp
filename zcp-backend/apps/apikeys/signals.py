from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_api_key(sender, instance, created, **kwargs):
    if created:
        from apps.apikeys.models import APIKey
        APIKey.objects.create(user=instance, name="Default")
