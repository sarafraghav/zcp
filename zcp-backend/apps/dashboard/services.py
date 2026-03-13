"""
Dashboard service layer — business logic for retrieving user dashboard data.
Returns typed Pydantic response models. Views call these functions.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# --- Response models ---

class NeonDatabaseResponse(BaseModel):
    id: str
    service_id: str
    project_id: str
    database_name: str
    connection_string: str
    status: str
    temporal_workflow_id: str
    created_at: datetime


class RedisResponse(BaseModel):
    id: str
    service_id: str
    database_id: str
    endpoint: str
    port: int
    password: str
    rest_token: str
    tls: bool
    status: str
    temporal_workflow_id: str
    created_at: datetime
    env_vars: list[tuple[str, str]]


class DeployedAppResponse(BaseModel):
    id: str
    app_name: str
    service_urls: dict
    status: str
    temporal_workflow_id: str
    created_at: datetime


class ProjectResponse(BaseModel):
    id: str
    name: str
    manifest: dict
    created_at: datetime
    databases: list[NeonDatabaseResponse] = []
    redis_instances: list[RedisResponse] = []
    deployed_apps: list[DeployedAppResponse] = []


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    role: str
    databases: list[NeonDatabaseResponse]
    redis_instances: list[RedisResponse]
    deployed_apps: list[DeployedAppResponse]
    projects: list[ProjectResponse]


class DashboardResponse(BaseModel):
    user_id: str
    email: str
    organizations: list[OrganizationResponse]


# --- Service function ---

def get_dashboard(user) -> DashboardResponse:
    from apps.accounts.models import ResourceAccessMapping

    mappings = (
        ResourceAccessMapping.objects
        .filter(user=user)
        .prefetch_related(
            "organization__databases",
            "organization__redis_instances",
            "organization__deployed_apps",
            "organization__projects",
        )
    )

    organizations = []
    for m in mappings:
        # Build flat resource lists (kept for backward compat)
        databases = []
        for d in m.organization.databases.all():
            databases.append(NeonDatabaseResponse(
                id=str(d.id),
                service_id=d.service_id,
                project_id=d.project_id,
                database_name=d.database_name,
                connection_string=d.connection_string,
                status=d.status,
                temporal_workflow_id=d.temporal_workflow_id,
                created_at=d.created_at,
            ))

        redis_instances = []
        for rdb in m.organization.redis_instances.all():
            redis_instances.append(RedisResponse(
                id=str(rdb.id),
                service_id=rdb.service_id,
                database_id=rdb.database_id,
                endpoint=rdb.endpoint,
                port=rdb.port,
                password=rdb.password,
                rest_token=rdb.rest_token,
                tls=rdb.tls,
                status=rdb.status,
                temporal_workflow_id=rdb.temporal_workflow_id,
                created_at=rdb.created_at,
                env_vars=[
                    ("REDIS_HOST", rdb.endpoint),
                    ("REDIS_PORT", str(rdb.port)),
                    ("REDIS_PASSWORD", rdb.password),
                    ("REDIS_DB", "0"),
                ],
            ))

        deployed_apps = []
        for da in m.organization.deployed_apps.all():
            deployed_apps.append(DeployedAppResponse(
                id=str(da.id),
                app_name=da.app_name,
                service_urls=da.service_urls,
                status=da.status,
                temporal_workflow_id=da.temporal_workflow_id,
                created_at=da.created_at,
            ))

        # Build project-grouped resources
        # Index resources by their zcp_project FK
        db_by_project: dict[Optional[str], list[NeonDatabaseResponse]] = {}
        for d in m.organization.databases.all():
            pk = str(d.zcp_project_id) if d.zcp_project_id else None
            resp = next((db for db in databases if db.id == str(d.id)), None)
            if resp:
                db_by_project.setdefault(pk, []).append(resp)

        redis_by_project: dict[Optional[str], list[RedisResponse]] = {}
        for rdb in m.organization.redis_instances.all():
            pk = str(rdb.zcp_project_id) if rdb.zcp_project_id else None
            resp = next((r for r in redis_instances if r.id == str(rdb.id)), None)
            if resp:
                redis_by_project.setdefault(pk, []).append(resp)

        apps_by_project: dict[Optional[str], list[DeployedAppResponse]] = {}
        for da in m.organization.deployed_apps.all():
            pk = str(da.zcp_project_id) if da.zcp_project_id else None
            resp = next((a for a in deployed_apps if a.id == str(da.id)), None)
            if resp:
                apps_by_project.setdefault(pk, []).append(resp)

        projects = []
        for p in m.organization.projects.all():
            pid = str(p.id)
            projects.append(ProjectResponse(
                id=pid,
                name=p.name,
                manifest=p.manifest,
                created_at=p.created_at,
                databases=db_by_project.get(pid, []),
                redis_instances=redis_by_project.get(pid, []),
                deployed_apps=apps_by_project.get(pid, []),
            ))

        organizations.append(OrganizationResponse(
            id=str(m.organization.id),
            name=m.organization.name,
            slug=m.organization.slug,
            role=m.role,
            databases=databases,
            redis_instances=redis_instances,
            deployed_apps=deployed_apps,
            projects=projects,
        ))

    return DashboardResponse(
        user_id=str(user.id),
        email=user.email,
        organizations=organizations,
    )
