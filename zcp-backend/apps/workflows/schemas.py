from pydantic import BaseModel


# --- Activity inputs/outputs ---

class CreateOrganizationInput(BaseModel):
    name: str
    slug: str


class CreateOrganizationOutput(BaseModel):
    org_id: str


class LinkUserToOrgInput(BaseModel):
    user_id: str
    org_id: str


class ProvisionNeonDatabaseInput(BaseModel):
    org_id: str
    slug: str
    workflow_id: str
    service_id: str = "default"
    project_id: str = ""


class ProvisionNeonDatabaseOutput(BaseModel):
    project_id: str
    database_name: str
    connection_string: str


class ProvisionRedisInput(BaseModel):
    org_id: str
    slug: str
    workflow_id: str
    service_id: str = "default"
    project_id: str = ""


class ProvisionRedisOutput(BaseModel):
    database_id: str
    endpoint: str
    port: int
    password: str
    rest_token: str


# --- Project activities ---

class CreateProjectInput(BaseModel):
    org_id: str
    name: str
    manifest: dict
    redeploy: bool = False


class CreateProjectOutput(BaseModel):
    project_id: str


# --- Deploy workflow activities ---

class CloneRepoInput(BaseModel):
    repo_url: str
    branch: str
    commit: str = ""


class CloneRepoOutput(BaseModel):
    manifest: dict
    source_path: str



class ModalDeployInput(BaseModel):
    org_id: str
    project_id: str
    slug: str
    app_name: str
    compute_services: list
    provisioned: dict
    source_path: str
    workflow_id: str


class ModalDeployOutput(BaseModel):
    service_urls: dict


class FlyDeployInput(BaseModel):
    org_id: str
    project_id: str
    slug: str
    app_name: str
    container_services: list
    provisioned: dict
    source_path: str  # needed to read configFiles content


class FlyDeployOutput(BaseModel):
    service_urls: dict


class UpsertDeployedAppInput(BaseModel):
    org_id: str
    project_id: str
    app_name: str
    service_urls: dict
    workflow_id: str


class CleanupSourceInput(BaseModel):
    source_path: str


# --- ProjectDeployWorkflow input ---

class ProjectDeployInput(BaseModel):
    org_id: str
    slug: str
    project_id: str = ""


# --- DeployWorkflow input/output ---

class DeployWorkflowInput(BaseModel):
    org_id: str
    slug: str
    manifest: dict
    source_path: str
    redeploy: bool = False


class DeployWorkflowOutput(BaseModel):
    project_id: str
    app_name: str
    service_urls: dict


# --- SignupWorkflow input/output ---

class SignupWorkflowInput(BaseModel):
    user_id: str
    org_name: str
    slug: str


class SignupWorkflowOutput(BaseModel):
    org_id: str
    app_name: str
    service_urls: dict
