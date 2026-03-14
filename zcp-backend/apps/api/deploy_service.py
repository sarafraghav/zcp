"""
Server-side deploy orchestration — starts a DeployWorkflow on Temporal.
"""
import uuid as _uuid

from apps.workflows.schemas import DeployWorkflowInput, DeployWorkflowOutput

TASK_QUEUE = "zcp-signup"


async def start_deploy_workflow(
    org_id: str,
    slug: str,
    manifest: dict,
    source_path: str,
) -> DeployWorkflowOutput:
    """Start DeployWorkflow and wait for it to complete. Returns the result."""
    from apps.workflows.client import get_temporal_client
    from apps.workflows.deploy import DeployWorkflow

    client = await get_temporal_client()
    workflow_id = f"deploy-{slug}-{_uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        DeployWorkflow.run,
        DeployWorkflowInput(
            org_id=org_id,
            slug=slug,
            manifest=manifest,
            source_path=source_path,
            redeploy=True,
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return await handle.result()
