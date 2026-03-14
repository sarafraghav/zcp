# zcp-cli

CLI for deploying apps to the [Zamp Control Plane](https://github.com/sarafraghav/zcp).

ZCP provisions databases (Neon Postgres), caches (Upstash Redis), and compute (Modal) from a single `zcp.json` manifest — no infra credentials needed on your machine.

## Install

```bash
pip install zcp-cli
```

## Quick start

```bash
# 1. Login with your API token (grab it from the ZCP dashboard)
zcp login --token zcp_...

# 2. Deploy (reads zcp.json in current directory)
zcp deploy

# Or point to a specific manifest
zcp deploy --file path/to/zcp.json --org-slug my-org
```

## Commands

### `zcp login`

Save your API token locally (`~/.zcp/config.json`, chmod 600).

```
zcp login --token <API_KEY> [--api-url https://your-zcp-server.com]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--token` | (required) | API key from ZCP dashboard |
| `--api-url` | `http://localhost:8000` | ZCP server URL |

You can also set `ZCP_API_TOKEN` and `ZCP_API_URL` environment variables.

### `zcp deploy`

Package your app source and deploy via the ZCP server.

```
zcp deploy [--file PATH] [--org-slug SLUG]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--file` | `./zcp.json` | Path to manifest |
| `--org-slug` | `name` from manifest | Target organization |

The CLI zips your source (excluding `node_modules`, `.git`, `.venv`, etc.), uploads it along with the manifest, and the server handles provisioning and deployment.

## `zcp.json` manifest

```json
{
  "name": "myapp",
  "services": [
    { "id": "db", "type": "postgres" },
    { "id": "cache", "type": "redis" },
    {
      "id": "api",
      "type": "web",
      "runtime": "python",
      "start": "gunicorn app:app --bind 0.0.0.0:5001",
      "port": 5001,
      "env": [
        { "name": "DATABASE_URL", "fromService": { "id": "db", "value": "connectionString" } },
        { "name": "REDIS_URL", "fromService": { "id": "cache", "value": "connectionString" } }
      ]
    }
  ]
}
```

## License

MIT
