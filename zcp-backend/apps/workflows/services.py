"""
Workflow service layer — business logic for starting and polling Temporal workflows.
Returns typed Pydantic response models. Views and the API layer both call these functions.
"""
import uuid as _uuid
from pydantic import BaseModel

from apps.workflows.schemas import SignupWorkflowInput

TASK_QUEUE = "zcp-signup"


# --- Response models ---

class SignupStartedResponse(BaseModel):
    workflow_id: str
    status: str = "running"


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    status: str  # running | completed | failed | terminated | timed_out


# --- Service functions ---

async def start_signup_workflow(
    user_id: str,
    org_name: str,
    slug: str,
) -> SignupStartedResponse:
    from apps.workflows.client import get_temporal_client
    from apps.workflows.signup import SignupWorkflow

    workflow_id = f"signup-{slug}-{_uuid.uuid4().hex[:8]}"
    client = await get_temporal_client()
    await client.start_workflow(
        SignupWorkflow.run,
        SignupWorkflowInput(user_id=user_id, org_name=org_name, slug=slug),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return SignupStartedResponse(workflow_id=workflow_id)


async def start_project_deploy_workflow(
    org_id: str,
    slug: str,
) -> SignupStartedResponse:
    """Start a deploy workflow for a new project within an existing org."""
    from apps.workflows.client import get_temporal_client
    from apps.workflows.deploy import ProjectDeployWorkflow
    from apps.workflows.schemas import ProjectDeployInput

    workflow_id = f"project-{slug}-{_uuid.uuid4().hex[:8]}"
    client = await get_temporal_client()
    await client.start_workflow(
        ProjectDeployWorkflow.run,
        ProjectDeployInput(org_id=org_id, slug=slug),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return SignupStartedResponse(workflow_id=workflow_id)


async def start_project_redeploy_workflow(
    org_id: str,
    slug: str,
    project_id: str,
) -> SignupStartedResponse:
    """Start a deploy workflow that redeploys an existing project."""
    from apps.workflows.client import get_temporal_client
    from apps.workflows.deploy import ProjectDeployWorkflow
    from apps.workflows.schemas import ProjectDeployInput

    workflow_id = f"redeploy-{slug}-{_uuid.uuid4().hex[:8]}"
    client = await get_temporal_client()
    await client.start_workflow(
        ProjectDeployWorkflow.run,
        ProjectDeployInput(org_id=org_id, slug=slug, project_id=project_id),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return SignupStartedResponse(workflow_id=workflow_id)


async def get_workflow_status(workflow_id: str) -> WorkflowStatusResponse:
    from apps.workflows.client import get_temporal_client

    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()
    return WorkflowStatusResponse(
        workflow_id=workflow_id,
        status=desc.status.name.lower(),
    )
