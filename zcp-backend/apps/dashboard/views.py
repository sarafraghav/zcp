"""
FE view layer — thin wrappers that call the service layer and render HTMX templates.
No business logic or direct DB/Temporal access lives here.
"""
import asyncio
import subprocess
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django_htmx.http import HttpResponseClientRedirect

from apps.accounts.models import User
from apps.accounts.forms import SignupForm
from apps.dashboard.forms import CreateOrgForm
from apps.workflows.services import start_signup_workflow, start_project_deploy_workflow, start_project_redeploy_workflow, get_workflow_status
from apps.dashboard.services import get_dashboard


def _active_org_id(request, dashboard):
    """Return the active org ID from session, defaulting to the first org."""
    orgs = dashboard.organizations
    if not orgs:
        return None
    stored = request.session.get("active_org_id")
    if stored and any(o.id == stored for o in orgs):
        return stored
    first_id = orgs[0].id
    request.session["active_org_id"] = first_id
    return first_id


# ─── Signup ──────────────────────────────────────────────────────────────

class SignupView(View):
    def get(self, request):
        return render(request, "signup/form.html", {"form": SignupForm()})

    def post(self, request):
        form = SignupForm(request.POST)
        if not form.is_valid():
            return render(request, "signup/form.html", {"form": form})

        # User created in Django — password never passes through Temporal
        user = form.save()

        # Store org info in session for the onboarding deploy step
        request.session["pending_org_name"] = form.cleaned_data["org_name"]
        request.session["pending_slug"] = form.cleaned_data["slug"]

        # Auto-login immediately
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        return redirect("onboarding:welcome")


class WorkflowStatusView(View):
    """Legacy status endpoint — still used for direct signup flows."""
    def get(self, request, workflow_id):
        status_response = asyncio.run(get_workflow_status(workflow_id))

        if status_response.status == "completed":
            user_id = request.session.pop("pending_signup_user_id", None)
            if user_id:
                user = User.objects.get(id=user_id)
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return HttpResponseClientRedirect("/dashboard/")

        return render(request, "signup/_status_partial.html", {
            "workflow_id": status_response.workflow_id,
            "status": status_response.status,
        })


# ─── Onboarding ─────────────────────────────────────────────────────────

class OnboardingWelcomeView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "onboarding/welcome.html")


class OnboardingSchemaView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "onboarding/schema.html")


class OnboardingApiKeyView(LoginRequiredMixin, View):
    def get(self, request):
        from apps.apikeys.models import APIKey
        if not APIKey.objects.filter(user=request.user).exists():
            APIKey.objects.create(user=request.user, name="Default")
        api_key = APIKey.objects.filter(user=request.user).first()
        return render(request, "onboarding/apikey.html", {"api_key": api_key})


class OnboardingDeployView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "onboarding/deploy.html")

    def post(self, request):
        org_name = request.session.get("pending_org_name")
        slug = request.session.get("pending_slug")
        if not org_name or not slug:
            # Fallback: generate from the user's email if session keys were lost
            email = request.user.email
            org_name = org_name or f"{email.split('@')[0]}'s Org"
            slug = slug or email.split("@")[0].lower().replace(".", "-").replace("+", "-")[:30]
            request.session["pending_org_name"] = org_name
            request.session["pending_slug"] = slug

        try:
            result = asyncio.run(start_signup_workflow(
                user_id=str(request.user.id),
                org_name=org_name,
                slug=slug,
            ))
        except Exception as exc:
            return render(request, "onboarding/deploy.html", {
                "error": f"Failed to start deploy: {exc}",
            })
        return render(request, "onboarding/status.html", {
            "workflow_id": result.workflow_id,
        })


class OnboardingDeployStatusView(LoginRequiredMixin, View):
    def get(self, request, workflow_id):
        status_response = asyncio.run(get_workflow_status(workflow_id))
        if status_response.status == "completed":
            # Clean up session
            request.session.pop("pending_org_name", None)
            request.session.pop("pending_slug", None)
            return HttpResponseClientRedirect("/dashboard/")
        return render(request, "onboarding/_status_partial.html", {
            "workflow_id": status_response.workflow_id,
            "status": status_response.status,
        })


# ─── Dashboard ───────────────────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        from apps.apikeys.models import APIKey
        # Lazy-create for existing users who signed up before apikeys app
        if not APIKey.objects.filter(user=request.user).exists():
            APIKey.objects.create(user=request.user, name="Default")

        dashboard = get_dashboard(request.user)
        active_id = _active_org_id(request, dashboard)
        active_org = next((o for o in dashboard.organizations if o.id == active_id), None)
        return render(request, "dashboard/index.html", {
            "dashboard": dashboard,
            "active_org": active_org,
        })


class DatabaseListView(LoginRequiredMixin, View):
    def get(self, request):
        dashboard = get_dashboard(request.user)
        active_id = request.session.get("active_org_id")
        databases = []
        for org in dashboard.organizations:
            if not active_id or org.id == active_id:
                databases.extend(org.databases)
        return render(request, "dashboard/_database_card.html", {"databases": databases})


class QueryDatabaseView(LoginRequiredMixin, View):
    def post(self, request, db_id):
        import psycopg2
        from apps.database.models import NeonDatabase
        from apps.accounts.models import ResourceAccessMapping

        db_record = get_object_or_404(NeonDatabase, id=db_id)

        if not ResourceAccessMapping.objects.filter(
            user=request.user, organization=db_record.organization
        ).exists():
            return HttpResponseBadRequest("Access denied.")

        sql = request.POST.get("sql", "").strip()
        if not sql:
            return render(request, "dashboard/_query_results.html", {"error": "No SQL provided."})
        if sql.split()[0].upper() != "SELECT":
            return render(request, "dashboard/_query_results.html", {"error": "Only SELECT statements are allowed."})

        try:
            conn = psycopg2.connect(db_record.connection_string)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchall()
            conn.close()
            return render(request, "dashboard/_query_results.html", {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            })
        except Exception as exc:
            return render(request, "dashboard/_query_results.html", {"error": str(exc)})


class RedisListView(LoginRequiredMixin, View):
    def get(self, request):
        dashboard = get_dashboard(request.user)
        active_id = request.session.get("active_org_id")
        redis_list = []
        for org in dashboard.organizations:
            if not active_id or org.id == active_id:
                redis_list.extend(org.redis_instances)
        return render(request, "dashboard/_redis_card.html", {"redis_list": redis_list})


class RedisCommandView(LoginRequiredMixin, View):
    def post(self, request, redis_id):
        import redis as redis_client
        from apps.redis.models import UpstashRedis
        from apps.accounts.models import ResourceAccessMapping

        r = get_object_or_404(UpstashRedis, id=redis_id)
        if not ResourceAccessMapping.objects.filter(user=request.user, organization=r.organization).exists():
            return HttpResponseBadRequest("Access denied.")

        command = request.POST.get("command", "").strip().upper()
        key = request.POST.get("key", "").strip()
        value = request.POST.get("value", "").strip()

        try:
            conn = redis_client.Redis(
                host=r.endpoint, port=r.port, password=r.password,
                ssl=r.tls, decode_responses=True, socket_timeout=10,
            )
            if command == "GET":
                val = conn.get(key)
                result = {"result": val}
            elif command == "SET" and value:
                conn.set(key, value)
                result = {"result": "OK"}
            else:
                result = {"result": None, "error": f"Unsupported command: {command}"}
            conn.close()
            return render(request, "dashboard/_redis_result.html", {"result": result})
        except Exception as exc:
            return render(request, "dashboard/_redis_result.html", {"error": str(exc)})


class AppsListView(LoginRequiredMixin, View):
    def get(self, request):
        dashboard = get_dashboard(request.user)
        active_id = request.session.get("active_org_id")
        apps = []
        for org in dashboard.organizations:
            if not active_id or org.id == active_id:
                apps.extend(org.deployed_apps)
        return render(request, "dashboard/_apps_card.html", {"apps": apps})


class CreateOrgView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "dashboard/create_org.html", {"form": CreateOrgForm()})

    def post(self, request):
        form = CreateOrgForm(request.POST)
        if not form.is_valid():
            return render(request, "dashboard/create_org.html", {"form": form})

        result = asyncio.run(start_signup_workflow(
            user_id=str(request.user.id),
            org_name=form.cleaned_data["org_name"],
            slug=form.cleaned_data["slug"],
        ))
        return render(request, "dashboard/create_org_status.html", {
            "workflow_id": result.workflow_id,
        })


class CreateProjectView(LoginRequiredMixin, View):
    def post(self, request):
        from apps.accounts.models import ResourceAccessMapping
        from apps.organizations.models import Organization

        active_org_id = request.session.get("active_org_id")
        if not active_org_id:
            return HttpResponseBadRequest("No active org.")

        if not ResourceAccessMapping.objects.filter(
            user=request.user, organization_id=active_org_id
        ).exists():
            return HttpResponseBadRequest("Access denied.")

        org = get_object_or_404(Organization, id=active_org_id)

        # Generate a unique slug: org_slug-pN where N is the next project number
        project_count = org.projects.count()
        project_slug = f"{org.slug}-p{project_count + 1}"

        result = asyncio.run(start_project_deploy_workflow(
            org_id=str(org.id),
            slug=project_slug,
        ))
        return render(request, "dashboard/create_project_status.html", {
            "workflow_id": result.workflow_id,
        })


class RedeployProjectView(LoginRequiredMixin, View):
    def post(self, request, project_id):
        from apps.accounts.models import ResourceAccessMapping
        from apps.projects.models import Project

        project = get_object_or_404(Project, id=project_id)
        org = project.organization

        if not ResourceAccessMapping.objects.filter(
            user=request.user, organization=org
        ).exists():
            return HttpResponseBadRequest("Access denied.")

        # Find the slug from the deployed app for this project
        deployed_app = org.deployed_apps.filter(zcp_project=project).first()
        if deployed_app:
            # Extract slug from app_name (format: "name-slug")
            slug = deployed_app.app_name.replace(f"{project.name}-", "", 1)
        else:
            slug = org.slug

        result = asyncio.run(start_project_redeploy_workflow(
            org_id=str(org.id),
            slug=slug,
            project_id=str(project.id),
        ))
        return render(request, "dashboard/create_project_status.html", {
            "workflow_id": result.workflow_id,
        })


class ProjectDeployStatusView(LoginRequiredMixin, View):
    def get(self, request, workflow_id):
        status_response = asyncio.run(get_workflow_status(workflow_id))
        if status_response.status == "completed":
            return HttpResponseClientRedirect("/dashboard/")
        return render(request, "dashboard/_project_status_partial.html", {
            "workflow_id": status_response.workflow_id,
            "status": status_response.status,
        })


class OrgWorkflowStatusView(LoginRequiredMixin, View):
    def get(self, request, workflow_id):
        status_response = asyncio.run(get_workflow_status(workflow_id))
        if status_response.status == "completed":
            return HttpResponseClientRedirect("/dashboard/")
        return render(request, "dashboard/_org_status_partial.html", {
            "workflow_id": status_response.workflow_id,
            "status": status_response.status,
        })


class SwitchOrgView(LoginRequiredMixin, View):
    def post(self, request, org_id):
        from apps.accounts.models import ResourceAccessMapping
        if not ResourceAccessMapping.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            return HttpResponseBadRequest("Access denied.")
        request.session["active_org_id"] = str(org_id)
        return redirect("dashboard:dashboard")


# In-memory deletion state: org_id (str) -> {"step": int, "status": "deleting|done|error", "error": str}
_DELETION_STEPS = [
    "Starting",
    "Stopping deployed services",
    "Deleting database",
    "Deleting cache",
    "Removing project records",
]
_deletion_state: dict = {}


class DeleteOrgView(LoginRequiredMixin, View):
    def post(self, request, org_id):
        import httpx
        import threading
        from django.conf import settings
        from apps.accounts.models import ResourceAccessMapping

        try:
            mapping = ResourceAccessMapping.objects.prefetch_related(
                "organization__databases",
                "organization__redis_instances",
                "organization__deployed_apps",
            ).get(user=request.user, organization_id=org_id, role="owner")
        except ResourceAccessMapping.DoesNotExist:
            return HttpResponseBadRequest("Access denied.")

        org = mapping.organization
        org_id_str = str(org_id)
        org_name = org.name

        # Gather resource IDs before background thread (avoids lazy-load across threads)
        redis_db_ids = list(org.redis_instances.values_list("database_id", flat=True))
        neon_project_ids = list(org.databases.values_list("project_id", flat=True))

        modal_app_names = list(org.deployed_apps.values_list("app_name", flat=True))

        _deletion_state[org_id_str] = {"step": 0, "status": "deleting", "error": ""}

        def do_delete():
            try:
                # Step 1 — Stop Modal apps
                _deletion_state[org_id_str]["step"] = 1
                for app_name in modal_app_names:
                    if app_name:
                        subprocess.run(
                            ["modal", "app", "stop", app_name],
                            timeout=30, capture_output=True,
                        )

                # Step 2 — Delete Neon projects
                _deletion_state[org_id_str]["step"] = 2
                for neon_pid in neon_project_ids:
                    if neon_pid:
                        httpx.delete(
                            f"https://console.neon.tech/api/v2/projects/{neon_pid}",
                            headers={"Authorization": f"Bearer {settings.NEON_API_KEY}"},
                            timeout=30,
                        )

                # Step 3 — Delete Fly.io Redis apps
                _deletion_state[org_id_str]["step"] = 3
                from apps.workflows.fly_engine import destroy_app
                for fly_app_name in redis_db_ids:
                    if fly_app_name:
                        destroy_app(settings.FLY_API_KEY, fly_app_name)

                # Step 4 — Delete Django records (cascades to all related models)
                _deletion_state[org_id_str]["step"] = 4
                from apps.organizations.models import Organization
                Organization.objects.filter(id=org_id).delete()

                _deletion_state[org_id_str]["status"] = "done"

            except Exception as exc:
                _deletion_state[org_id_str]["status"] = "error"
                _deletion_state[org_id_str]["error"] = str(exc)

        threading.Thread(target=do_delete, daemon=True).start()

        if request.session.get("active_org_id") == org_id_str:
            request.session.pop("active_org_id", None)

        return render(request, "dashboard/delete_org_status.html", {
            "org_id": org_id_str,
            "org_name": org_name,
            "steps": _DELETION_STEPS,
            "step": 0,
            "status": "deleting",
        })


class DeleteOrgStatusView(LoginRequiredMixin, View):
    def get(self, request, org_id):
        org_id_str = str(org_id)
        state = _deletion_state.get(org_id_str, {"step": 0, "status": "deleting", "error": ""})
        if state["status"] == "done":
            del _deletion_state[org_id_str]
            return HttpResponseClientRedirect("/dashboard/")
        return render(request, "dashboard/_delete_status_partial.html", {
            "org_id": org_id_str,
            "step": state["step"],
            "status": state["status"],
            "error": state.get("error", ""),
            "steps": _DELETION_STEPS,
        })


class APIKeyListView(LoginRequiredMixin, View):
    def get(self, request):
        from apps.apikeys.models import APIKey
        keys = APIKey.objects.filter(user=request.user)
        return render(request, "dashboard/_apikey_card.html", {"api_keys": keys})


class RegenerateAPIKeyView(LoginRequiredMixin, View):
    def post(self, request, key_id):
        from apps.apikeys.models import APIKey
        key = get_object_or_404(APIKey, id=key_id, user=request.user)
        key.rotate()
        keys = APIKey.objects.filter(user=request.user)
        return render(request, "dashboard/_apikey_card.html", {"api_keys": keys})
