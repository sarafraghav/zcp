import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UpstashRedis",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("database_id", models.CharField(blank=True, max_length=255)),
                ("endpoint", models.CharField(blank=True, max_length=255)),
                ("port", models.IntegerField(default=6379)),
                ("password", models.TextField(blank=True)),
                ("rest_token", models.TextField(blank=True)),
                ("tls", models.BooleanField(default=True)),
                ("status", models.CharField(
                    choices=[("provisioning", "Provisioning"), ("ready", "Ready"), ("error", "Error")],
                    default="provisioning",
                    max_length=20,
                )),
                ("metadata", models.JSONField(default=dict)),
                ("temporal_workflow_id", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="redis",
                    to="organizations.organization",
                )),
            ],
        ),
    ]
