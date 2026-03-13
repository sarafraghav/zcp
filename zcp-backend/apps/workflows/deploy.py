"""
DeployWorkflow — Temporal workflow that provisions infra, resolves env refs,
runs Modal deploy, and creates/updates DeployedApp records.

Used by both:
  - SignupWorkflow (as a child workflow, after cloning the sample repo)
  - DeployView API (started directly with uploaded source)
"""
import asyncio
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from apps.workflows.schemas import (
    CreateProjectInput, CreateProjectOutput,
    CloneRepoInput, CloneRepoOutput,
    InitDatabaseSchemaInput,
    ModalDeployInput, ModalDeployOutput,
    CleanupSourceInput,
    DeployWorkflowInput, DeployWorkflowOutput,
    ProvisionNeonDatabaseInput, ProvisionNeonDatabaseOutput,
    ProvisionRedisInput, ProvisionRedisOutput,
)

with workflow.unsafe.imports_passed_through():
    import json

_INFRA_TYPES = {"postgres", "redis"}


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@activity.defn
async def create_project_activity(params: CreateProjectInput) -> CreateProjectOutput:
    from apps.projects.models import Project
    from apps.organizations.models import Organization

    org = await Organization.objects.aget(id=params.org_id)
    project = await Project.objects.acreate(
        organization=org,
        name=params.name,
        manifest=params.manifest,
    )
    return CreateProjectOutput(project_id=str(project.id))


@activity.defn
async def clone_repo_activity(params: CloneRepoInput) -> CloneRepoOutput:
    """Clone a git repo. If repo_url/branch are empty, reads from Django settings."""
    import subprocess
    import tempfile
    from pathlib import Path
    from django.conf import settings

    repo_url = params.repo_url or settings.SAMPLE_REPO_URL
    branch = params.branch or settings.SAMPLE_REPO_BRANCH
    commit = params.commit or settings.SAMPLE_REPO_COMMIT

    clone_dir = Path(tempfile.mkdtemp(prefix="zcp_repo_"))
    clone_cmd = ["git", "clone", "--depth", "1", "--branch", branch,
                 repo_url, str(clone_dir)]
    result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr}")

    if commit:
        subprocess.run(["git", "fetch", "--unshallow"],
                       cwd=str(clone_dir), capture_output=True, text=True, timeout=120)
        checkout = subprocess.run(["git", "checkout", commit],
                                  cwd=str(clone_dir), capture_output=True, text=True, timeout=30)
        if checkout.returncode != 0:
            raise RuntimeError(f"git checkout {commit} failed: {checkout.stderr}")

    manifest_path = clone_dir / "zcp.json"
    if not manifest_path.exists():
        raise RuntimeError(f"zcp.json not found in cloned repo at {clone_dir}")

    raw_manifest = json.loads(manifest_path.read_text())

    # Validate against the canonical zcp.json schema
    from apps.docs.schema import validate_and_dump
    manifest = validate_and_dump(raw_manifest)

    return CloneRepoOutput(manifest=manifest, source_path=str(clone_dir))


@activity.defn
async def init_database_schema_activity(params: InitDatabaseSchemaInput) -> None:
    """Run init SQL against a provisioned database (e.g. CREATE TABLE statements)."""
    import psycopg2
    conn = psycopg2.connect(params.connection_string)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(params.sql)
    finally:
        conn.close()


@activity.defn
async def modal_deploy_activity(params: ModalDeployInput) -> ModalDeployOutput:
    """Resolve fromService env refs, detect runtimes, run Modal deploy."""
    from pathlib import Path
    from apps.workflows.deploy_engine import detect_runtime
    from apps.deployments.models import DeployedApp
    from apps.organizations.models import Organization

    source_path = Path(params.source_path)

    # Resolve fromService references
    patched = []
    for svc in params.compute_services:
        svc = dict(svc)
        svc["env"] = _resolve_env(svc.get("env", []), params.provisioned)
        if not svc.get("runtime"):
            base_path = source_path / svc.get("basePath", svc["id"])
            svc["runtime"] = detect_runtime(base_path)
        patched.append(svc)

    # Two-pass Modal deploy
    all_urls = _two_pass_deploy(params.app_name, params.slug, patched, source_path)

    # Create/update DeployedApp record
    org = await Organization.objects.aget(id=params.org_id)
    project_kwargs = {}
    if params.project_id:
        from apps.projects.models import Project
        project_kwargs["zcp_project"] = await Project.objects.aget(id=params.project_id)

    await DeployedApp.objects.aupdate_or_create(
        organization=org,
        app_name=f"{params.app_name}-{params.slug}",
        defaults={
            "service_urls": all_urls,
            "status": "ready",
            "temporal_workflow_id": params.workflow_id,
            "metadata": {"deployed_via": "workflow"},
            **project_kwargs,
        },
    )

    return ModalDeployOutput(service_urls=all_urls)


@activity.defn
async def cleanup_source_activity(params: CleanupSourceInput) -> None:
    import shutil
    from pathlib import Path
    path = Path(params.source_path)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers (pure functions, safe for activity context)
# ---------------------------------------------------------------------------

def _resolve_env(raw_env: list, provisioned: dict) -> list:
    resolved = []
    for entry in raw_env:
        entry = dict(entry)
        if "fromService" in entry:
            ref = entry["fromService"]
            ref_id, ref_field = ref["id"], ref["value"]
            if ref_id not in provisioned:
                raise ValueError(f"env '{entry['name']}': fromService id '{ref_id}' not found. "
                                 f"Provisioned: {list(provisioned)}")
            outputs = provisioned[ref_id]
            if ref_field not in outputs:
                raise ValueError(f"env '{entry['name']}': field '{ref_field}' not in '{ref_id}'. "
                                 f"Available: {list(outputs)}")
            entry = {"name": entry["name"], "value": str(outputs[ref_field])}
        resolved.append(entry)
    return resolved


def _two_pass_deploy(app_name, org_slug, services, app_root):
    from apps.workflows.deploy_engine import run_deploy

    non_next = [s for s in services if s.get("runtime") != "nextjs"]
    next_svcs = [s for s in services if s.get("runtime") == "nextjs"]
    web_non_next = [s for s in non_next if s.get("type", "web") == "web"]

    if web_non_next and next_svcs:
        backend_urls = run_deploy(app_name, org_slug, non_next, app_root)
        api_url = backend_urls.get("api") or (list(backend_urls.values())[0] if backend_urls else None)
        full_urls = run_deploy(app_name, org_slug, services, app_root, api_url=api_url)
        return {**backend_urls, **full_urls}
    else:
        return run_deploy(app_name, org_slug, services, app_root)


# ---------------------------------------------------------------------------
# DeployWorkflow
# ---------------------------------------------------------------------------

@workflow.defn
class DeployWorkflow:
    @workflow.run
    async def run(self, params: DeployWorkflowInput) -> DeployWorkflowOutput:
        retry = RetryPolicy(maximum_attempts=3)
        manifest = params.manifest
        app_name = manifest["name"]
        all_services = manifest["services"]
        infra_services = [s for s in all_services if s.get("type") in _INFRA_TYPES]
        compute_services = [s for s in all_services if s.get("type") not in _INFRA_TYPES]
        wf_id = workflow.info().workflow_id

        # 1. Create project record
        project_result = await workflow.execute_activity(
            create_project_activity,
            CreateProjectInput(org_id=params.org_id, name=app_name, manifest=manifest),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=retry,
        )

        # 2. Provision infra in parallel
        # Use string-based dispatch for activities defined in signup.py
        infra_tasks = []  # list of (svc_type, svc_dict, coroutine)
        for svc in infra_services:
            if svc["type"] == "postgres":
                infra_tasks.append(("postgres", svc, workflow.execute_activity(
                    "provision_neon_database_activity",
                    ProvisionNeonDatabaseInput(
                        org_id=params.org_id, slug=params.slug,
                        workflow_id=wf_id, service_id=svc["id"],
                        project_id=project_result.project_id,
                    ),
                    result_type=ProvisionNeonDatabaseOutput,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry,
                )))
            elif svc["type"] == "redis":
                infra_tasks.append(("redis", svc, workflow.execute_activity(
                    "provision_upstash_redis_activity",
                    ProvisionRedisInput(
                        org_id=params.org_id, slug=params.slug,
                        workflow_id=wf_id, service_id=svc["id"],
                        project_id=project_result.project_id,
                    ),
                    result_type=ProvisionRedisOutput,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry,
                )))

        provisioned = {}
        if infra_tasks:
            results = await asyncio.gather(*[t[2] for t in infra_tasks])
            for (svc_type, svc, _), result in zip(infra_tasks, results):
                if svc_type == "postgres":
                    provisioned[svc["id"]] = {
                        "connectionString": result.connection_string,
                        "project_id": result.project_id,
                        "database_name": result.database_name,
                    }
                elif svc_type == "redis":
                    provisioned[svc["id"]] = {
                        "connectionString": f"rediss://:{result.password}@{result.endpoint}:{result.port}",
                        "host": result.endpoint,
                        "port": str(result.port),
                        "authToken": result.password,
                        "restToken": result.rest_token,
                    }

        # 3. Run schema init for postgres services that have a "schema" field
        for svc in infra_services:
            if svc["type"] == "postgres" and svc.get("schema") and svc["id"] in provisioned:
                await workflow.execute_activity(
                    init_database_schema_activity,
                    InitDatabaseSchemaInput(
                        connection_string=provisioned[svc["id"]]["connectionString"],
                        sql=svc["schema"],
                    ),
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry,
                )

        # 4. Modal deploy
        deploy_result = await workflow.execute_activity(
            modal_deploy_activity,
            ModalDeployInput(
                org_id=params.org_id,
                project_id=project_result.project_id,
                slug=params.slug,
                app_name=app_name,
                compute_services=compute_services,
                provisioned=provisioned,
                source_path=params.source_path,
                workflow_id=wf_id,
            ),
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return DeployWorkflowOutput(
            project_id=project_result.project_id,
            app_name=f"{app_name}-{params.slug}",
            service_urls=deploy_result.service_urls,
        )
