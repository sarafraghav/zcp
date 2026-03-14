"""
DeployWorkflow — Temporal workflow that provisions infra, resolves env refs,
deploys compute to Modal and containers to Fly.io, and creates/updates DeployedApp records.

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
    ModalDeployInput, ModalDeployOutput,
    FlyDeployInput, FlyDeployOutput,
    CleanupSourceInput,
    UpsertDeployedAppInput,
    ProjectDeployInput,
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

    # Redeploy: reuse existing project if it exists
    if params.redeploy:
        try:
            project = await Project.objects.aget(organization=org, name=params.name)
            project.manifest = params.manifest
            await project.asave(update_fields=["manifest"])
            return CreateProjectOutput(project_id=str(project.id))
        except Project.DoesNotExist:
            pass  # Fall through to create new

    # Auto-deduplicate project name within the org
    base_name = params.name
    name = base_name
    counter = 1
    while await Project.objects.filter(organization=org, name=name).aexists():
        counter += 1
        name = f"{base_name}-{counter}"

    project = await Project.objects.acreate(
        organization=org,
        name=name,
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
async def modal_deploy_activity(params: ModalDeployInput) -> ModalDeployOutput:
    """Resolve fromService env refs, detect runtimes, run Modal deploy."""
    from pathlib import Path
    from apps.workflows.deploy_engine import detect_runtime

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

    return ModalDeployOutput(service_urls=all_urls)


@activity.defn
async def fly_deploy_activity(params: FlyDeployInput) -> FlyDeployOutput:
    """Deploy container services to Fly.io via the Machines API."""
    from pathlib import Path
    from django.conf import settings
    from apps.workflows.fly_engine import deploy_container

    source_path = Path(params.source_path)
    api_key = settings.FLY_API_KEY
    if not api_key:
        raise RuntimeError("FLY_API_KEY not configured — required for container services")

    all_urls = {}
    for svc in params.container_services:
        svc = dict(svc)
        # Resolve fromService env references
        svc["env"] = _resolve_env(svc.get("env", []), params.provisioned)
        env_vars = {e["name"]: e["value"] for e in svc["env"] if "value" in e}

        # Read configFiles content from the source directory
        config_files_content = {}
        for container_path, local_path in svc.get("configFiles", {}).items():
            file_path = source_path / local_path
            if not file_path.exists():
                raise RuntimeError(
                    f"configFile '{local_path}' not found at {file_path} "
                    f"for container service '{svc['id']}'"
                )
            config_files_content[container_path] = file_path.read_text()

        url = deploy_container(
            api_key=api_key,
            svc=svc,
            env_vars=env_vars,
            config_files_content=config_files_content,
            org_slug=params.slug,
            app_name=params.app_name,
        )
        if url:
            all_urls[svc["id"]] = url

    return FlyDeployOutput(service_urls=all_urls)


@activity.defn
async def cleanup_source_activity(params: CleanupSourceInput) -> None:
    import shutil
    from pathlib import Path
    path = Path(params.source_path)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


@activity.defn
async def upsert_deployed_app_activity(params: UpsertDeployedAppInput) -> None:
    """Create or update the DeployedApp record after deploy completes."""
    from apps.organizations.models import Organization
    from apps.deployments.models import DeployedApp

    org = await Organization.objects.aget(id=params.org_id)
    extra_kwargs = {}
    if params.project_id:
        from apps.projects.models import Project
        extra_kwargs["zcp_project"] = await Project.objects.aget(id=params.project_id)

    await DeployedApp.objects.aupdate_or_create(
        organization=org,
        app_name=params.app_name,
        defaults={
            "service_urls": params.service_urls,
            "status": "ready",
            "temporal_workflow_id": params.workflow_id,
            "metadata": {"deployed_via": "workflow"},
            **extra_kwargs,
        },
    )


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

        # 1. Create project record (redeploy reuses existing)
        project_result = await workflow.execute_activity(
            create_project_activity,
            CreateProjectInput(org_id=params.org_id, name=app_name, manifest=manifest, redeploy=params.redeploy),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=retry,
        )

        # 2. Provision infra in parallel
        # Use string-based dispatch for activities defined in signup.py
        # Prefix service_id with project ID so each project gets its own
        # Neon/Redis records (unique_together = org + service_id)
        proj_prefix = project_result.project_id[:8]
        infra_tasks = []  # list of (svc_type, svc_dict, coroutine)
        for svc in infra_services:
            scoped_service_id = f"{proj_prefix}-{svc['id']}"
            if svc["type"] == "postgres":
                infra_tasks.append(("postgres", svc, workflow.execute_activity(
                    "provision_neon_database_activity",
                    ProvisionNeonDatabaseInput(
                        org_id=params.org_id, slug=params.slug,
                        workflow_id=wf_id, service_id=scoped_service_id,
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
                        workflow_id=wf_id, service_id=scoped_service_id,
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

        # 3. Deploy compute: Modal for web/worker, Fly.io for container
        modal_services = [s for s in compute_services if s.get("type") != "container"]
        container_services = [s for s in compute_services if s.get("type") == "container"]

        deploy_tasks = []

        if modal_services:
            deploy_tasks.append(workflow.execute_activity(
                modal_deploy_activity,
                ModalDeployInput(
                    org_id=params.org_id,
                    project_id=project_result.project_id,
                    slug=params.slug,
                    app_name=app_name,
                    compute_services=modal_services,
                    provisioned=provisioned,
                    source_path=params.source_path,
                    workflow_id=wf_id,
                ),
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(maximum_attempts=2),
            ))

        if container_services:
            deploy_tasks.append(workflow.execute_activity(
                fly_deploy_activity,
                FlyDeployInput(
                    org_id=params.org_id,
                    project_id=project_result.project_id,
                    slug=params.slug,
                    app_name=app_name,
                    container_services=container_services,
                    provisioned=provisioned,
                    source_path=params.source_path,
                ),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2),
            ))

        # Run Modal + Fly deploys in parallel
        all_urls = {}
        if deploy_tasks:
            results = await asyncio.gather(*deploy_tasks)
            for result in results:
                all_urls.update(result.service_urls)

        # Create/update DeployedApp record
        await workflow.execute_activity(
            upsert_deployed_app_activity,
            UpsertDeployedAppInput(
                org_id=params.org_id,
                project_id=project_result.project_id,
                app_name=f"{app_name}-{params.slug}",
                service_urls=all_urls,
                workflow_id=wf_id,
            ),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return DeployWorkflowOutput(
            project_id=project_result.project_id,
            app_name=f"{app_name}-{params.slug}",
            service_urls=all_urls,
        )


# ---------------------------------------------------------------------------
# ProjectDeployWorkflow — clone sample repo → DeployWorkflow → cleanup
# ---------------------------------------------------------------------------

@workflow.defn
class ProjectDeployWorkflow:
    """Deploys a new project within an existing org."""

    @workflow.run
    async def run(self, params: ProjectDeployInput) -> DeployWorkflowOutput:
        retry = RetryPolicy(maximum_attempts=3)

        # 1. Clone sample repo (empty params → reads from Django settings)
        clone_result: CloneRepoOutput = await workflow.execute_activity(
            clone_repo_activity,
            CloneRepoInput(repo_url="", branch="", commit=""),
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )

        # 2. Deploy via child workflow
        redeploy = bool(params.project_id)
        deploy_result: DeployWorkflowOutput = await workflow.execute_child_workflow(
            "DeployWorkflow",
            DeployWorkflowInput(
                org_id=params.org_id,
                slug=params.slug,
                manifest=clone_result.manifest,
                source_path=clone_result.source_path,
                redeploy=redeploy,
            ),
            id=f"deploy-proj-{params.slug}-{workflow.info().workflow_id}",
            result_type=DeployWorkflowOutput,
        )

        # 3. Cleanup cloned source
        await workflow.execute_activity(
            cleanup_source_activity,
            CleanupSourceInput(source_path=clone_result.source_path),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=retry,
        )

        return deploy_result
