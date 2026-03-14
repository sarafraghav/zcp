"""
Fly.io Deploy Engine — deploys pre-built container images via the Machines API.

Used for `container` service types in zcp.json. Unlike Modal (which requires Python
in every image), Fly.io runs Docker images natively with full ENTRYPOINT/CMD support.

API reference: https://fly.io/docs/machines/api/machines-resource/
"""
import base64
import shlex
import time

import httpx

FLY_API_BASE = "https://api.machines.dev/v1"
FLY_WAIT_TIMEOUT = 120  # seconds to wait for machine to start (includes image pull)


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _create_app(api_key: str, app_name: str) -> None:
    """Create a Fly app. Idempotent — ignores 'already exists' errors."""
    resp = httpx.post(
        f"{FLY_API_BASE}/apps",
        headers=_headers(api_key),
        json={"app_name": app_name, "org_slug": "personal"},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        return
    # Check if it's an "already exists" error (safe to ignore)
    body = resp.text
    if "already" in body.lower():
        return
    resp.raise_for_status()


FLY_GRAPHQL = "https://api.fly.io/graphql"

_ALLOCATE_IP_MUTATION = """
mutation($input: AllocateIPAddressInput!) {
  allocateIpAddress(input: $input) {
    ipAddress { id address type }
  }
}
"""


def _allocate_ips(api_key: str, app_name: str) -> None:
    """Allocate shared IPv4 + IPv6 for the app via GraphQL. Idempotent."""
    for ip_type in ["shared_v4", "v6"]:
        httpx.post(
            FLY_GRAPHQL,
            headers=_headers(api_key),
            json={
                "query": _ALLOCATE_IP_MUTATION,
                "variables": {"input": {"appId": app_name, "type": ip_type}},
            },
            timeout=30,
        )
        # Ignore errors — IP may already be allocated


def deploy_container(
    api_key: str,
    svc: dict,
    env_vars: dict,
    config_files_content: dict[str, str],
    org_slug: str,
    app_name: str,
) -> str | None:
    """
    Deploy a single container service to Fly.io.

    Args:
        api_key: Fly.io API token
        svc: The container service dict from zcp.json
        env_vars: Resolved environment variables (fromService refs already resolved)
        config_files_content: {container_path: file_content_string}
        org_slug: Organization slug (used in app naming)
        app_name: Application name from zcp.json

    Returns:
        Public URL (https://<app>.fly.dev) if the service has a port, else None.
    """
    svc_id = svc["id"]
    # Fly app names must be globally unique, lowercase, alphanumeric + hyphens
    fly_app = f"zcp-{app_name}-{org_slug}-{svc_id}".lower().replace("_", "-")

    # 1. Create the Fly app
    _create_app(api_key, fly_app)

    # 2. Allocate IPs for public services
    port = svc.get("port")
    if port:
        _allocate_ips(api_key, fly_app)

    # 3. Build machine config
    machine_config = {
        "image": svc["image"],
        "env": env_vars,
        "guest": {
            "cpu_kind": "shared",
            "cpus": 1,
            "memory_mb": 256,
        },
    }

    # Command override — uses cmd (Docker CMD) which gets appended to the
    # image's ENTRYPOINT. E.g. for oryd/kratos (ENTRYPOINT ["kratos"]),
    # command "serve --dev" → kratos serve --dev
    cmd = svc.get("command")
    if cmd:
        machine_config["init"] = {"cmd": shlex.split(cmd)}

    # Port exposure — Fly handles TLS termination
    if port:
        machine_config["services"] = [
            {
                "ports": [
                    {"port": 80, "handlers": ["http"]},
                    {"port": 443, "handlers": ["tls", "http"]},
                ],
                "protocol": "tcp",
                "internal_port": port,
            }
        ]

    # Config files — injected directly into the machine filesystem
    if config_files_content:
        machine_config["files"] = [
            {
                "guest_path": container_path,
                "raw_value": base64.b64encode(content.encode()).decode(),
            }
            for container_path, content in config_files_content.items()
        ]

    # Scaling
    scaling = svc.get("scaling", {})
    min_containers = scaling.get("min", 1)
    # Fly auto_destroy + auto_start handles scale-to-zero
    if min_containers == 0:
        machine_config["auto_destroy"] = True

    # 4. Create the machine
    resp = httpx.post(
        f"{FLY_API_BASE}/apps/{fly_app}/machines",
        headers=_headers(api_key),
        json={"config": machine_config},
        timeout=60,
    )
    if not resp.is_success:
        raise RuntimeError(f"Fly machine create failed ({resp.status_code}): {resp.text}")
    machine_id = resp.json()["id"]

    # 5. Wait for machine to start
    _wait_for_machine(api_key, fly_app, machine_id)

    if port:
        return f"https://{fly_app}.fly.dev"
    return None


def _wait_for_machine(api_key: str, app_name: str, machine_id: str) -> None:
    """Poll until the machine reaches 'started' state."""
    deadline = time.time() + FLY_WAIT_TIMEOUT
    while time.time() < deadline:
        resp = httpx.get(
            f"{FLY_API_BASE}/apps/{app_name}/machines/{machine_id}",
            headers=_headers(api_key),
            timeout=15,
        )
        resp.raise_for_status()
        state = resp.json().get("state")
        if state == "started":
            return
        if state in ("failed", "destroyed"):
            raise RuntimeError(f"Fly machine {machine_id} entered state: {state}")
        time.sleep(2)
    raise RuntimeError(f"Fly machine {machine_id} did not start within {FLY_WAIT_TIMEOUT}s")


def destroy_app(api_key: str, app_name: str) -> None:
    """Delete a Fly app and all its machines."""
    resp = httpx.delete(
        f"{FLY_API_BASE}/apps/{app_name}",
        headers=_headers(api_key),
        timeout=30,
    )
    if resp.status_code == 404:
        return  # Already gone
    resp.raise_for_status()
