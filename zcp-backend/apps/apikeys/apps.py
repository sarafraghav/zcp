from django.apps import AppConfig


class ApiKeysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.apikeys"
    verbose_name = "API Keys"

    def ready(self):
        import apps.apikeys.signals  # noqa: F401
