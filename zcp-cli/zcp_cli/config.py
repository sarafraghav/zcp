import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".zcp"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    CONFIG_FILE.chmod(0o600)


def get_token() -> str | None:
    return os.environ.get("ZCP_API_TOKEN") or load_config().get("token")


def get_api_url() -> str:
    return os.environ.get("ZCP_API_URL") or load_config().get("api_url", "http://localhost:8000")
