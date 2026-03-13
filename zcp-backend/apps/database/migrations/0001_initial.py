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
            name="NeonDatabase",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("project_id", models.CharField(blank=True, max_length=255)),
                ("database_name", models.CharField(blank=True, max_length=255)),
                ("connection_string", models.TextField(blank=True)),
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
                    related_name="database",
                    to="organizations.organization",
                )),
            ],
        ),
    ]
