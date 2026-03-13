import asyncio
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from apps.workflows.schemas import (
    CreateOrganizationInput, CreateOrganizationOutput,
    LinkUserToOrgInput,
    ProvisionNeonDatabaseInput, ProvisionNeonDatabaseOutput,
    ProvisionRedisInput, ProvisionRedisOutput,
    CloneRepoInput, CloneRepoOutput,
    CleanupSourceInput,
    DeployWorkflowInput, DeployWorkflowOutput,
    SignupWorkflowInput, SignupWorkflowOutput,
)

with workflow.unsafe.imports_passed_through():
    import httpx


@activity.defn
async def create_organization_activity(params: CreateOrganizationInput) -> CreateOrganizationOutput:
    from apps.organizations.models import Organization
    org = await Organization.objects.acreate(name=params.name, slug=params.slug)
    return CreateOrganizationOutput(org_id=str(org.id))


@activity.defn
async def link_user_to_org_activity(params: LinkUserToOrgInput) -> None:
    from apps.accounts.models import ResourceAccessMapping, User
    from apps.organizations.models import Organization
    user = await User.objects.aget(id=params.user_id)
    org = await Organization.objects.aget(id=params.org_id)
    await ResourceAccessMapping.objects.acreate(user=user, organization=org, role="owner")


@activity.defn
async def provision_neon_database_activity(params: ProvisionNeonDatabaseInput) -> ProvisionNeonDatabaseOutput:
    from django.conf import settings
    from apps.database.models import NeonDatabase
    from apps.organizations.models import Organization

    org = await Organization.objects.aget(id=params.org_id)

    # Idempotent: if record already exists (Temporal retry), skip API call and return stored data
    try:
        db_record = await NeonDatabase.objects.aget(organization=org, service_id=params.service_id)
        if db_record.status == "ready":
            return ProvisionNeonDatabaseOutput(
                project_id=db_record.project_id,
                database_name=db_record.database_name,
                connection_string=db_record.connection_string,
            )
    except NeonDatabase.DoesNotExist:
        project_kwargs = {}
        if params.project_id:
            from apps.projects.models import Project
            project_kwargs["zcp_project"] = await Project.objects.aget(id=params.project_id)
        db_record = await NeonDatabase.objects.acreate(
            organization=org,
            service_id=params.service_id,
            temporal_workflow_id=params.workflow_id,
            status="provisioning",
            **project_kwargs,
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://console.neon.tech/api/v2/projects",
            headers={"Authorization": f"Bearer {settings.NEON_API_KEY}"},
            json={"project": {"name": f"zcp-{params.slug}", "region_id": "aws-us-east-2", "org_id": settings.NEON_ORG_ID}},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()

    project_id = data["project"]["id"]
    connection_string = data["connection_uris"][0]["connection_uri"]
    database_name = data["databases"][0]["name"]

    db_record.project_id = project_id
    db_record.database_name = database_name
    db_record.connection_string = connection_string
    db_record.status = "ready"
    db_record.metadata = {"project_id": project_id, "database_name": database_name}
    await db_record.asave()

    return ProvisionNeonDatabaseOutput(
        project_id=project_id,
        database_name=database_name,
        connection_string=connection_string,
    )


@activity.defn
async def provision_upstash_redis_activity(params: ProvisionRedisInput) -> ProvisionRedisOutput:
    from django.conf import settings
    from apps.redis.models import UpstashRedis
    from apps.organizations.models import Organization

    org = await Organization.objects.aget(id=params.org_id)
    try:
        r = await UpstashRedis.objects.aget(organization=org, service_id=params.service_id)
        if r.status == "ready":
            return ProvisionRedisOutput(
                database_id=r.database_id, endpoint=r.endpoint,
                port=r.port, password=r.password, rest_token=r.rest_token,
            )
    except UpstashRedis.DoesNotExist:
        project_kwargs = {}
        if params.project_id:
            from apps.projects.models import Project
            project_kwargs["zcp_project"] = await Project.objects.aget(id=params.project_id)
        r = await UpstashRedis.objects.acreate(
            organization=org, service_id=params.service_id,
            temporal_workflow_id=params.workflow_id, status="provisioning",
            **project_kwargs,
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.upstash.com/v2/redis/database",
            auth=(settings.UPSTASH_EMAIL, settings.UPSTASH_API_KEY),
            json={"database_name": f"zcp-{params.slug}", "platform": "aws", "primary_region": "us-east-1", "tls": True},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()

    r.database_id = data["database_id"]
    r.endpoint = data["endpoint"]
    r.port = data["port"]
    r.password = data["password"]
    r.rest_token = data["rest_token"]
    r.status = "ready"
    r.metadata = {"database_id": data["database_id"], "endpoint": data["endpoint"]}
    await r.asave()

    return ProvisionRedisOutput(
        database_id=r.database_id, endpoint=r.endpoint,
        port=r.port, password=r.password, rest_token=r.rest_token,
    )


@workflow.defn
class SignupWorkflow:
    @workflow.run
    async def run(self, params: SignupWorkflowInput) -> SignupWorkflowOutput:
        retry = RetryPolicy(maximum_attempts=3)
        timeout = timedelta(minutes=2)

        # 1. Create org
        org_result: CreateOrganizationOutput = await workflow.execute_activity(
            create_organization_activity,
            CreateOrganizationInput(name=params.org_name, slug=params.slug),
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        # 2. Link user to org
        await workflow.execute_activity(
            link_user_to_org_activity,
            LinkUserToOrgInput(user_id=params.user_id, org_id=org_result.org_id),
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        # 3. Clone sample repo (empty params → activity reads from Django settings)
        clone_result: CloneRepoOutput = await workflow.execute_activity(
            "clone_repo_activity",
            CloneRepoInput(repo_url="", branch="", commit=""),
            result_type=CloneRepoOutput,
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        # 4. Deploy via child workflow
        deploy_result: DeployWorkflowOutput = await workflow.execute_child_workflow(
            "DeployWorkflow",
            DeployWorkflowInput(
                org_id=org_result.org_id,
                slug=params.slug,
                manifest=clone_result.manifest,
                source_path=clone_result.source_path,
            ),
            id=f"deploy-{params.slug}-{workflow.info().workflow_id}",
            result_type=DeployWorkflowOutput,
        )

        # 5. Cleanup cloned source
        await workflow.execute_activity(
            "cleanup_source_activity",
            CleanupSourceInput(source_path=clone_result.source_path),
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=retry,
        )

        return SignupWorkflowOutput(
            org_id=org_result.org_id,
            app_name=deploy_result.app_name,
            service_urls=deploy_result.service_urls,
        )
