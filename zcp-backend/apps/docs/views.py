import json

from django.shortcuts import render
from django.views import View

from apps.docs.schema import ZcpManifest


class SpecView(View):
    """Renders the zcp.json specification page."""

    def get(self, request):
        schema = ZcpManifest.model_json_schema()
        return render(request, "docs/spec.html", {
            "schema_json": json.dumps(schema, indent=2),
        })


class SchemaJsonView(View):
    """Serves the raw JSON Schema for editor integration ($schema)."""

    def get(self, request):
        from django.http import JsonResponse
        schema = ZcpManifest.model_json_schema()
        return JsonResponse(schema)
