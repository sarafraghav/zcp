"""
Pydantic models for the zcp.json manifest spec.

These models serve as both the validation layer and the source-of-truth for
the published JSON Schema (via ZcpManifest.model_json_schema()).
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

class FromServiceRef(BaseModel):
    """Reference to an output field from another service."""
    id: str = Field(description="The `id` of the infra service to reference (e.g. `maindb`, `cache`).")
    value: str = Field(description=(
        "The output field to read. "
        "Postgres: `connectionString`, `project_id`, `database_name`. "
        "Redis: `connectionString`, `host`, `port`, `authToken`, `restToken`."
    ))


class LiteralEnvVar(BaseModel):
    """An environment variable with a static value."""
    name: str = Field(description="Environment variable name.")
    value: str = Field(description="Static string value.")


class RefEnvVar(BaseModel):
    """An environment variable whose value comes from another service's output."""
    name: str = Field(description="Environment variable name.")
    fromService: FromServiceRef = Field(description="Service output reference.")


EnvVar = Annotated[Union[RefEnvVar, LiteralEnvVar], Field(discriminator=None)]


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------

class ScalingConfig(BaseModel):
    """Autoscaling configuration for compute services."""
    min: int = Field(default=1, ge=0, description="Minimum number of containers. `0` enables scale-to-zero.")
    max: int = Field(default=3, ge=1, description="Maximum number of containers.")


# ---------------------------------------------------------------------------
# Service types
# ---------------------------------------------------------------------------

class PostgresService(BaseModel):
    """Provisions a serverless Postgres database via Neon."""
    id: str = Field(description="Unique identifier used in `fromService` references.")
    type: Literal["postgres"]


class RedisService(BaseModel):
    """Provisions a Redis cache via Upstash."""
    id: str = Field(description="Unique identifier used in `fromService` references.")
    type: Literal["redis"]


class WebService(BaseModel):
    """A compute service with a public HTTP endpoint, deployed to Modal."""
    id: str = Field(description="Unique identifier. Also used as the function name in the generated Modal app.")
    type: Literal["web"] = Field(default="web")
    runtime: str | None = Field(
        default=None,
        description=(
            "Runtime to use. Auto-detected from source if omitted. "
            "Supported: `python`, `nodejs`, `nextjs`, `docker`, `go`."
        ),
    )
    basePath: str | None = Field(
        default=None,
        description="Directory containing the service source, relative to `zcp.json`. Defaults to the service `id`.",
    )
    start: str = Field(description="Shell command to start the service (e.g. `gunicorn app:app --bind 0.0.0.0:5001`).")
    port: int = Field(default=8000, description="Port the service listens on.")
    scaling: ScalingConfig = Field(default_factory=ScalingConfig, description="Autoscaling configuration.")
    env: list[EnvVar] = Field(default_factory=list, description="Environment variables — static values or `fromService` references.")


class WorkerService(BaseModel):
    """A background compute service with no HTTP endpoint, deployed to Modal."""
    id: str = Field(description="Unique identifier.")
    type: Literal["worker"]
    runtime: str | None = Field(
        default=None,
        description="Runtime to use. Auto-detected from source if omitted.",
    )
    basePath: str | None = Field(
        default=None,
        description="Directory containing the service source, relative to `zcp.json`. Defaults to the service `id`.",
    )
    start: str = Field(description="Shell command to start the worker process.")
    scaling: ScalingConfig = Field(default_factory=ScalingConfig, description="Autoscaling configuration.")
    env: list[EnvVar] = Field(default_factory=list, description="Environment variables.")


class ContainerService(BaseModel):
    """A service deployed from a pre-built container image (e.g. Docker Hub, GHCR)."""
    id: str = Field(description="Unique identifier.")
    type: Literal["container"]
    image: str = Field(description="Registry image reference (e.g. `oryd/kratos:v1.3.1`).")
    command: str | None = Field(default=None, description=(
        "Override the image's default CMD/ENTRYPOINT. If omitted, the image's defaults are used. "
        "E.g. `kratos serve --config /etc/config/kratos/kratos.yml`."
    ))
    port: int | None = Field(default=None, description="If set, expose as a public HTTP endpoint. If omitted, run as a background worker.")
    configFiles: dict[str, str] = Field(
        default_factory=dict,
        description="Map of container destination path to local file path (relative to `zcp.json`). Files are baked into the image at build time.",
    )
    scaling: ScalingConfig = Field(default_factory=ScalingConfig, description="Autoscaling configuration.")
    env: list[EnvVar] = Field(default_factory=list, description="Environment variables.")


Service = Annotated[
    Union[PostgresService, RedisService, WebService, WorkerService, ContainerService],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------

class ZcpManifest(BaseModel):
    """
    Root schema for `zcp.json` — the deployment manifest for the Zamp Control Plane.

    All infrastructure and compute resources are declared as entries in the
    `services` array. Infra services (postgres, redis) are provisioned first;
    compute services (web, worker) reference infra outputs via `fromService`.
    """
    name: str = Field(description="Application name. Used as the Modal app prefix (combined with org slug).")
    services: list[Service] = Field(description="List of infrastructure and compute service definitions.")


def validate_manifest(raw: dict) -> ZcpManifest:
    """Validate a raw dict against the zcp.json schema. Raises ``ValidationError`` on failure."""
    return ZcpManifest.model_validate(raw)


def validate_and_dump(raw: dict) -> dict:
    """Validate and return a clean dict suitable for downstream processing."""
    return validate_manifest(raw).model_dump(exclude_none=True)
