"""
ZCP Deploy Engine — generates Modal Python code that bakes source into images
via add_local_dir. No Modal Volumes required.

Source files are resolved relative to app_root (the directory containing zcp.json).
Service types:
  web    — public HTTP endpoint via @modal.web_server(port)
  worker — private background process via @app.function only (no HTTP)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def _py_id(svc_id: str) -> str:
    """Convert a service ID to a valid Python identifier (hyphens → underscores)."""
    return svc_id.replace("-", "_").replace(".", "_")


def detect_runtime(base_path: Path) -> str:
    if (base_path / "Dockerfile").exists():
        return "docker"
    if (base_path / "package.json").exists():
        pkg = json.loads((base_path / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        return "nextjs" if "next" in deps else "nodejs"
    if (base_path / "requirements.txt").exists() or (base_path / "pyproject.toml").exists():
        return "python"
    if (base_path / "go.mod").exists():
        return "go"
    raise ValueError(f"Cannot detect runtime in {base_path}")


def build_image_code(svc_id, runtime, base_path: Path, env_vars: dict) -> str:
    """
    Bakes source into the image with add_local_dir.
    Always uses absolute path so Modal can find files regardless of CWD at deploy time.
    svc_id is sanitized to a valid Python identifier via _py_id().
    """
    var = _py_id(svc_id)
    abs_path = str(base_path.resolve())
    env_str = json.dumps(env_vars) if env_vars else "{}"
    if runtime == "python":
        reqs = base_path / "requirements.txt"
        pkgs = []
        if reqs.exists():
            pkgs = [l.strip() for l in reqs.read_text().splitlines()
                    if l.strip() and not l.startswith("#")]
        all_pkgs = ["gunicorn"] + pkgs
        pkgs_str = ", ".join(f'"{p}"' for p in all_pkgs)
        env_line = f'\n    .env({env_str})' if env_vars else ''
        return (f'_{var}_image = (\n'
                f'    modal.Image.debian_slim(python_version="3.11")\n'
                f'    .pip_install({pkgs_str})\n'
                f'    .add_local_dir("{abs_path}", "/app", copy=True){env_line}\n'
                f')')
    elif runtime in ("nextjs", "nodejs"):
        # CRITICAL: .env() BEFORE .run_commands() so NEXT_PUBLIC_* vars are baked
        # into the Next.js bundle at image-build time.
        env_line = f'\n    .env({env_str})' if env_vars else ''
        return (f'_{var}_image = (\n'
                f'    modal.Image.debian_slim()\n'
                f'    .apt_install("curl")\n'
                f'    .run_commands(\n'
                f'        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",\n'
                f'        "apt-get install -y nodejs"\n'
                f'    )\n'
                f'    .add_local_dir("{abs_path}", "/app", copy=True){env_line}\n'
                f'    .run_commands("cd /app && npm install", "cd /app && npm run build")\n'
                f')')
    elif runtime == "docker":
        env_line = f'\n    .env({env_str})' if env_vars else ''
        return (f'_{var}_image = (\n'
                f'    modal.Image.from_dockerfile("{abs_path}/Dockerfile"){env_line}\n'
                f')')
    raise ValueError(f"Unsupported runtime: {runtime}")


def build_function_code(svc, runtime) -> str:
    """
    Generates a Modal function for the service.
    type "web" (default): @modal.web_server decorator for public HTTP.
    type "worker": @app.function only — blocking subprocess, no HTTP endpoint.
    Function name uses _py_id() so hyphens in service IDs don't break Python syntax.
    """
    svc_id = svc["id"]
    var = _py_id(svc_id)
    svc_type = svc.get("type", "web")
    min_c = svc.get("scaling", {}).get("min", 1)
    max_c = svc.get("scaling", {}).get("max", 3)
    start_cmd = svc["start"]
    cmd_list = json.dumps(start_cmd.split())

    if svc_type == "worker":
        # No web_server decorator. Runs start command as a blocking subprocess.
        return (
            f'@app.function(\n'
            f'    image=_{var}_image,\n'
            f'    min_containers={min_c},\n'
            f'    max_containers={max_c},\n'
            f')\n'
            f'def {var}():\n'
            f'    import subprocess\n'
            f'    subprocess.run(["bash", "-c", {json.dumps(start_cmd)}])\n'
        )

    # Default: web service
    port = svc.get("port", 8000)
    # Next.js build is done at image-build time; startup just runs `npm start`
    startup_timeout = 120 if runtime in ("nextjs", "nodejs") else 60
    return (
        f'@app.function(\n'
        f'    image=_{var}_image,\n'
        f'    min_containers={min_c},\n'
        f'    max_containers={max_c},\n'
        f')\n'
        f'@modal.web_server({port}, startup_timeout={startup_timeout})\n'
        f'def {var}():\n'
        f'    import subprocess\n'
        f'    subprocess.Popen({cmd_list})\n'
    )


def generate_modal_code(app_name, org_slug, services, app_root: Path, api_url=None) -> str:
    # Each org gets its own Modal app so deployments don't overwrite each other.
    modal_app_name = f"{app_name}-{org_slug}"
    lines = ["import modal", "", f'app = modal.App("{modal_app_name}")', ""]
    for svc in services:
        base_path = app_root / svc.get("basePath", svc["id"])
        runtime = svc.get("runtime") or detect_runtime(base_path)
        env_vars = {e["name"]: e["value"] for e in svc.get("env", []) if "value" in e}
        if runtime == "nextjs" and api_url:
            env_vars["NEXT_PUBLIC_API_URL"] = api_url
        lines.append(build_image_code(svc["id"], runtime, base_path, env_vars))
        lines.append("")
        lines.append(build_function_code(svc, runtime))
    return "\n".join(lines)


def run_deploy(app_name, org_slug, services, app_root: Path, api_url=None) -> dict:
    code = generate_modal_code(app_name, org_slug, services, app_root, api_url)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix="zcp_") as f:
        f.write(code)
        tmp_path = f.name
    print(f"\n=== Generated Modal app: {tmp_path} ===", file=sys.stderr)
    print(code, file=sys.stderr)
    print(f"\n=== Deploying to Modal ===", file=sys.stderr)
    result = subprocess.run(
        ["modal", "deploy", tmp_path],
        capture_output=True, text=True, env=dict(os.environ),
    )
    combined = result.stdout + "\n" + result.stderr
    print(combined, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Modal deploy failed (exit {result.returncode}):\n{combined}")
    urls = {}
    web_services = [s for s in services if s.get("type", "web") == "web"]
    all_found = re.findall(r'https://[a-z0-9-]+--[a-z0-9-]+\.modal\.run', combined)
    for url in all_found:
        for svc in web_services:
            if svc["id"] in url:
                urls[svc["id"]] = url
    if not urls:
        for i, url in enumerate(all_found):
            if i < len(web_services):
                urls[web_services[i]["id"]] = url
    return urls
