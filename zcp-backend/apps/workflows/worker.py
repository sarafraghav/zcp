"""
Standalone Temporal worker. Run with:
    uv run python -m apps.workflows.worker
"""
import asyncio
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zcp.settings")
django.setup()

from temporalio.worker import Worker

from apps.workflows.client import get_temporal_client
from apps.workflows.signup import (
    SignupWorkflow,
    create_organization_activity,
    link_user_to_org_activity,
    provision_neon_database_activity,
    provision_upstash_redis_activity,
)
from apps.workflows.deploy import (
    DeployWorkflow,
    ProjectDeployWorkflow,
    create_project_activity,
    clone_repo_activity,
    modal_deploy_activity,
    cleanup_source_activity,
)

TASK_QUEUE = "zcp-signup"


async def main():
    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[SignupWorkflow, DeployWorkflow, ProjectDeployWorkflow],
        activities=[
            create_organization_activity,
            link_user_to_org_activity,
            provision_neon_database_activity,
            provision_upstash_redis_activity,
            create_project_activity,
            clone_repo_activity,
            modal_deploy_activity,
            cleanup_source_activity,
        ],
    )
    print(f"Worker started on task queue: {TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
