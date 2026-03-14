"""
ZCP CLI — deploy apps via the ZCP server.

Commands:
  zcp login --token <api-key> [--api-url URL]
  zcp deploy [--file PATH] [--org-slug SLUG]
"""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

from zcp_cli.config import get_token, get_api_url, save_config, load_config
from zcp_cli.api_client import ZCPClient

_ZIP_EXCLUDE = {
    "node_modules", "__pycache__", ".git", ".venv", ".zcp",
    ".next", ".DS_Store", "dist", "build", ".egg-info",
}
_ZIP_EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}


def _zip_source(app_root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(app_root.rglob("*")):
            if any(part in _ZIP_EXCLUDE for part in path.relative_to(app_root).parts):
                continue
            if path.suffix in _ZIP_EXCLUDE_EXTENSIONS:
                continue
            if path.is_file():
                zf.write(path, path.relative_to(app_root))
    buf.seek(0)
    return buf.getvalue()


def _run_login(args):
    config = load_config()
    config["token"] = args.token
    if args.api_url:
        config["api_url"] = args.api_url
    save_config(config)
    api_url = args.api_url or config.get("api_url", "http://localhost:8000")
    print(f"Logged in. Token saved to ~/.zcp/config.json (server: {api_url})")


def _run_deploy(args):
    token = get_token()
    if not token:
        print("Error: no API token. Run `zcp login --token <token>` first.",
              file=sys.stderr)
        sys.exit(1)

    api_url = get_api_url()
    client = ZCPClient(api_url=api_url, token=token)

    zcp_file = Path(args.file).resolve() if args.file else Path.cwd() / "zcp.json"
    if not zcp_file.exists():
        print(f"Error: {zcp_file} not found.", file=sys.stderr)
        sys.exit(1)

    app_root = zcp_file.parent.resolve()
    manifest = json.loads(zcp_file.read_text())
    org_slug = args.org_slug or manifest["name"]

    print(f"Packaging source from {app_root}...", file=sys.stderr)
    source_zip = _zip_source(app_root)
    print(f"  {len(source_zip) / 1024:.0f} KB compressed", file=sys.stderr)

    print(f"Deploying to {api_url} (org: {org_slug})...", file=sys.stderr)
    result = client.deploy(
        manifest=json.dumps(manifest),
        org_slug=org_slug,
        source_zip=source_zip,
    )

    print("\n=== DEPLOY COMPLETE ===")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="zcp",
        description="ZCP — deploy apps via the ZCP server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lp = subparsers.add_parser("login", help="Save API token")
    lp.add_argument("--token", required=True, help="API key from ZCP dashboard")
    lp.add_argument("--api-url", help="ZCP server URL (default: https://zcp-backend.onrender.com)")

    dp = subparsers.add_parser("deploy", help="Deploy services from zcp.json")
    dp.add_argument("--file", metavar="PATH", help="Path to zcp.json")
    dp.add_argument("--org-slug", metavar="SLUG", help="Org slug (default: app name)")

    args = parser.parse_args()
    if args.command == "login":
        _run_login(args)
    elif args.command == "deploy":
        _run_deploy(args)


if __name__ == "__main__":
    main()
