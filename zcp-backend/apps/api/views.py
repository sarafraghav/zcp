import json
import shutil
import asyncio
import tempfile
import zipfile
from pathlib import Path

from pydantic import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework import status

from apps.api.deploy_service import start_deploy_workflow
from apps.docs.schema import validate_and_dump


class DeployView(APIView):
    """
    POST /api/v1/deploy/
    Content-Type: multipart/form-data
    Authorization: Bearer zcp_...

    Fields:
      manifest  — JSON string (contents of zcp.json)
      org_slug  — string
      source    — zip file of the project directory
    """
    parser_classes = [MultiPartParser]

    def post(self, request):
        from apps.organizations.models import Organization
        from apps.accounts.models import ResourceAccessMapping

        # --- Parse & validate manifest against zcp.json schema ---
        try:
            raw_manifest = json.loads(request.data.get("manifest", ""))
        except (json.JSONDecodeError, TypeError):
            return Response({"error": "Invalid manifest JSON."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            manifest = validate_and_dump(raw_manifest)
        except ValidationError as e:
            return Response({"error": "Invalid manifest.", "details": e.errors()}, status=status.HTTP_400_BAD_REQUEST)

        org_slug = request.data.get("org_slug", "").strip()
        if not org_slug:
            return Response({"error": "org_slug is required."}, status=status.HTTP_400_BAD_REQUEST)

        source_file = request.FILES.get("source")
        if not source_file:
            return Response({"error": "source zip file is required."}, status=status.HTTP_400_BAD_REQUEST)

        # --- Get or create org; ensure user has access ---
        org, created = Organization.objects.get_or_create(
            slug=org_slug, defaults={"name": org_slug}
        )
        if created:
            ResourceAccessMapping.objects.create(
                user=request.user, organization=org, role="owner"
            )
        else:
            if not ResourceAccessMapping.objects.filter(
                user=request.user, organization=org
            ).exists():
                return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        # --- Extract zip to temp dir ---
        temp_dir = Path(tempfile.mkdtemp(prefix="zcp_deploy_"))
        try:
            with zipfile.ZipFile(source_file, "r") as zf:
                zf.extractall(temp_dir)

            # Start DeployWorkflow and wait for result
            result = asyncio.run(start_deploy_workflow(
                org_id=str(org.id),
                slug=org_slug,
                manifest=manifest,
                source_path=str(temp_dir),
            ))

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return Response({
            "app": result.app_name,
            "project_id": result.project_id,
            "services": result.service_urls,
        })
