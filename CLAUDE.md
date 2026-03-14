# ZCP — Claude Working Instructions

## Core Obligations

### 1. Keep CLAUDE.md current
If architecture, conventions, URLs, or standing instructions change, update this file in the same turn.
Add inline docstrings/comments where logic is non-obvious.

If the user gives standing instructions or asks to "remember" something, record it here immediately.

### 2. Testing is mandatory before responding
Every code change must be followed by all three test layers **in the same turn**:
1. **API / Django check** — `uv run python manage.py check` and direct Python assertions
2. **Temporal workflow** — start worker, trigger `SignupWorkflow`, assert result + DB state
3. **Browser (agent-browser)** — use the `npx agent-browser` skill to exercise the full UI flow

Do not respond with "done" until all three pass. Keep iterating silently until tests pass.

---

## Project Overview

**Zamp Control Plane (ZCP)** — Django 5 app that lets users sign up, triggering a Temporal
workflow that provisions their Organization, User, ResourceAccessMapping, Neon database,
Upstash Redis, and deploys a sample app to Modal.

**Stack:**
- Django 5.2 + Django REST Framework
- HTMX (via `django-htmx`) for reactive frontend without a JS build step
- Tailwind CSS (CDN) for styling; theme system in `templates/_theme.html`
- Temporal Cloud for workflow orchestration (`zcp-raghav.dkqth` namespace)
- Modal for app deployment (`add_local_dir` bakes source into images — no volumes)
- SQLite (dev), python-decouple for env config

---

## Pydantic Schemas (Temporal)

All workflow and activity inputs/outputs are typed Pydantic models defined in `apps/workflows/schemas.py`. Every activity takes exactly one Pydantic model argument and returns one (or `None`).

| Schema | Used by |
|--------|---------|
| `SignupWorkflowInput` | `SignupWorkflow.run` input |
| `SignupWorkflowOutput` | `SignupWorkflow.run` output |
| `CreateOrganizationInput/Output` | `create_organization_activity` |
| `LinkUserToOrgInput` | `link_user_to_org_activity` |
| `ProvisionNeonDatabaseInput/Output` | `provision_neon_database_activity` |
| `ProvisionRedisInput/Output` | `provision_upstash_redis_activity` |
| `DeployFromRepoInput/Output` | `deploy_from_repo_activity` |

The `pydantic_data_converter` from `temporalio.contrib.pydantic` is set on the **client** (`apps/workflows/client.py`). The worker inherits it automatically.

**Never pass raw dicts or positional args to Temporal activities** — always use the schema model.

---

## App Structure

```
pyproject.toml          # Workspace root — members: ["zcp-backend", "zcp-cli"]
zcp-backend/            # Django backend
  zcp/                  # Django project config (settings, urls, wsgi, asgi)
  apps/
    accounts/           # Custom User (AbstractUser) + ResourceAccessMapping
    organizations/      # Organization model
    database/           # NeonDatabase — multiple per org (ForeignKey + service_id)
    redis/              # UpstashRedis — multiple per org (ForeignKey + service_id)
    deployments/        # DeployedApp — one per org, auto-deployed via Modal during signup
    workflows/          # Temporal SignupWorkflow + activities + worker + deploy_engine
    dashboard/          # HTMX views for signup, status polling, dashboard
    apikeys/            # APIKey model — user-level API tokens for CLI auth
    api/                # REST API — DeployView (server-side deploy orchestration)
  templates/
    _theme.html         # CSS variable theme system (4 themes); all templates use semantic classes
    base.html           # Tailwind + HTMX CDN, nav with theme switcher
    signup/             # form.html, status.html, _status_partial.html (HTMX partial)
    dashboard/          # index.html, _database_card.html, _query_results.html,
                        # _redis_card.html, _redis_result.html, _apps_card.html,
                        # _apikey_card.html, create_org.html, create_org_status.html
    registration/       # login.html (Django auth convention)
  Sample Deployment/    # Example app (tictactoe) with zcp.json manifest
  manage.py
  pyproject.toml
zcp-cli/                # Thin CLI client (httpx only, no Modal/Neon/Upstash)
  zcp_cli/              # config.py, api_client.py, cli.py
  pyproject.toml
```

---

## Key Models

| Model | App | Notes |
|-------|-----|-------|
| `User` | `accounts` | `AbstractUser`; `AUTH_USER_MODEL = "accounts.User"` |
| `ResourceAccessMapping` | `accounts` | Links User ↔ Organization with a role |
| `Organization` | `organizations` | UUID PK, unique slug |
| `NeonDatabase` | `database` | ForeignKey to Org (`related_name="databases"`); `unique_together = (organization, service_id)` |
| `UpstashRedis` | `redis` | ForeignKey to Org (`related_name="redis_instances"`); `unique_together = (organization, service_id)` |
| `DeployedApp` | `deployments` | One-to-one with Org; tracks app_name, service_urls (JSON), status, workflow ID |
| `APIKey` | `apikeys` | ForeignKey to User (`related_name="api_keys"`); `zcp_` prefixed token; auto-created on user signup |

**No `ModalVolume` / `volumes` app** — deleted. Source is baked into Modal images via `add_local_dir`.

---

## URLs

| URL | View | Auth |
|-----|------|------|
| `/` | Redirect → `/dashboard/` | — |
| `/signup/` | `SignupView` (GET form, POST start workflow) | No |
| `/signup/status/<wf_id>/` | `WorkflowStatusView` (HTMX poll; auto-login + redirect on complete) | No |
| `/dashboard/` | `DashboardView` | `LoginRequired` |
| `/dashboard/databases/` | `DatabaseListView` (HTMX partial) | `LoginRequired` |
| `/dashboard/databases/<db_id>/query/` | `QueryDatabaseView` (POST; SELECT only, enforced) | `LoginRequired` |
| `/dashboard/redis/` | `RedisListView` (HTMX partial) | `LoginRequired` |
| `/dashboard/redis/<redis_id>/command/` | `RedisCommandView` (POST; GET/SET via Upstash HTTP API) | `LoginRequired` |
| `/dashboard/apps/` | `AppsListView` (HTMX partial) | `LoginRequired` |
| `/dashboard/orgs/create/` | `CreateOrgView` | `LoginRequired` |
| `/dashboard/orgs/status/<wf_id>/` | `OrgWorkflowStatusView` (HTMX poll) | `LoginRequired` |
| `/dashboard/orgs/<org_id>/switch/` | `SwitchOrgView` (POST) | `LoginRequired` |
| `/dashboard/orgs/<org_id>/delete/` | `DeleteOrgView` (POST; cascades to all infra) | `LoginRequired` |
| `/dashboard/apikeys/` | `APIKeyListView` (HTMX partial) | `LoginRequired` |
| `/dashboard/apikeys/<key_id>/regenerate/` | `RegenerateAPIKeyView` (POST) | `LoginRequired` |
| `/api/v1/deploy/` | `DeployView` (POST multipart: manifest + source zip) | API key (`Bearer zcp_...`) |
| `/accounts/login/` | Django `LoginView` | No |
| `/accounts/logout/` | Django `LogoutView` (POST only — Django 5) → redirects to `/accounts/login/` | — |
| `/admin/` | Django admin | Staff |

---

## Signup Form

Uses `SignupForm(UserCreationForm)` from `apps/accounts/forms.py`. Fields: `email`, `password1`, `password2`, `org_name`, `slug`. The form saves the user with `username = email`. Template renders via `{% for field in form %}` loop. Password validation is handled by Django's built-in validators.

---

## Signup Flow

1. User fills `/signup/` → `SignupForm` validates → **user created in Django** (password stays on this server, never sent to Temporal)
   - `user_id` stored in `request.session["pending_signup_user_id"]`
   - Workflow started with `SignupWorkflowInput(user_id, org_name, slug)` — no password
2. HTMX status partial polls `/signup/status/<wf_id>/` every 2s
3. Worker runs 3 activities: create org → link user to org → `deploy_from_repo_activity`
4. `deploy_from_repo_activity` clones a pinned git repo (configured via `SAMPLE_REPO_URL` / `SAMPLE_REPO_BRANCH` / `SAMPLE_REPO_COMMIT` in settings), reads `zcp.json` from the clone, and calls `orchestrate_deploy()` which provisions infra, resolves `fromService` refs, and runs two-pass Modal deploy.
5. When Temporal reports `COMPLETED`:
   - `WorkflowStatusView` fetches the result, gets `user_id`, calls `login()`
   - Returns `HX-Redirect` → `/dashboard/` (via `HttpResponseClientRedirect`)
   - Browser navigates to dashboard, already authenticated

---

## Temporal

- **Cloud host:** `zcp-raghav.dkqth.tmprl.cloud:7233`
- **Namespace:** `zcp-raghav.dkqth`
- **API key:** in `.env` as `TEMPORAL_API_KEY`
- **Task queue:** `zcp-signup`
- **Worker entrypoint:** `cd zcp-backend && uv run python -m apps.workflows.worker`
- **Activities:** `create_organization_activity`, `link_user_to_org_activity`, `provision_neon_database_activity`, `provision_upstash_redis_activity`, `deploy_from_repo_activity`
- **Deploy engine:** `apps/workflows/deploy_engine.py` — `generate_modal_code` / `run_deploy` accept `app_root: Path` explicitly (no module-level global). Called by `deploy_app_activity`.
- **No `create_user_activity`** — user is created in the Django view before the workflow starts; password never enters Temporal history
- **No `provision_modal_volume_activity`** — volumes deleted; source baked into images
- **No `deploy_app_activity`** — replaced by `deploy_from_repo_activity` which clones a pinned repo and uses `orchestrate_deploy()` from `apps/api/deploy_service.py`

---

## Modal Deploy Engine (`apps/workflows/deploy_engine.py`)

Source files are baked into Modal images at deploy time via `.add_local_dir(abs_path, "/app", copy=True)`.
Always uses `base_path.resolve()` for absolute paths so Modal can find files regardless of CWD.

**Service types:**

| Type | HTTP | Modal decorator | Use case |
|------|------|-----------------|----------|
| `web` (default) | Public, via port | `@modal.web_server(port)` | APIs, frontends |
| `worker` | None | `@app.function` only | Temporal workers, queues, background jobs |

**Container services (`type: "container"`)** are deployed to **Fly.io** (not Modal) via the Machines API.
See `apps/workflows/fly_engine.py`. Fly.io runs Docker images natively — no Python requirement, no Dockerfile generation.

| Container variant | HTTP | Fly.io behavior | Use case |
|-------------------|------|-----------------|----------|
| `container` (with port) | Public HTTPS via `*.fly.dev` | Fly Machine + shared IPv4 | Pre-built images needing HTTP (e.g. Kratos) |
| `container` (no port) | None | Fly Machine (no services) | Pre-built images as background workers |

**Two-pass deploy** (used when any service has `runtime: "nextjs"`):
1. Pass 1: non-Next.js web services only → capture API URL
2. Pass 2: all services with `NEXT_PUBLIC_API_URL` injected

**Next.js build** happens at image-build time (`.run_commands("npm install", "npm run build")`), not at startup. `NEXT_PUBLIC_*` env vars must be set via `.env()` **before** `.run_commands()` to be baked into the bundle.

---

## ZCP CLI (`packages/cli/zcp_cli/cli.py`)

Thin client that packages source + manifest and POSTs to the server. **No local Neon/Upstash/Modal credentials needed** — only a ZCP API token.

```bash
# Login (stores token in ~/.zcp/config.json)
uv run zcp login --token zcp_... [--api-url http://localhost:8000]

# Deploy (reads zcp.json, zips source, POSTs to server)
uv run zcp deploy [--file PATH] [--org-slug SLUG]
```

- CLI dependency: `httpx` only (no modal, no neon, no upstash)
- Source zip excludes: `node_modules/`, `.next/`, `__pycache__/`, `.git/`, `.venv/`, `.zcp/`, `.DS_Store`
- Token stored in `~/.zcp/config.json` (chmod 600); also reads `ZCP_API_TOKEN` env var
- Installed as workspace member: `packages/cli/` with `zcp-cli` in root deps

## Server-Side Deploy API (`apps/api/`)

`POST /api/v1/deploy/` — multipart form: `manifest` (JSON string), `org_slug`, `source` (zip).

Server orchestrates everything:
1. Get/create org for the authenticated user
2. Provision postgres + redis concurrently (idempotent, via existing activities)
3. Resolve `fromService` refs (DATABASE_URL, REDIS_URL, etc.)
4. Extract source zip to temp dir
5. Detect runtimes, run modal deploy (two-pass if nextjs)
6. Create/update `DeployedApp` record
7. Return JSON with service URLs

Authentication: `Bearer zcp_...` header → `APIKeyAuthentication` → looks up `APIKey` model.

## API Keys (`apps/apikeys/`)

- Auto-created on user signup via `post_save` signal
- Lazy-created in `DashboardView` for existing users
- Token format: `zcp_` + 32 bytes of `secrets.token_urlsafe` (256-bit entropy)
- Stored plaintext (capability token, not password — must be displayed in dashboard)
- Dashboard card shows token with copy button + regenerate

---

## `zcp.json` Schema (Flightcontrol-inspired)

All resources — databases, caches, compute — are entries in the `services` array.

```jsonc
{
  "name": "myapp",
  "services": [
    // Infra: provisioned before compute, outputs referenced via fromService
    { "id": "maindb", "type": "postgres" },  // → Neon
    { "id": "cache",  "type": "redis"    },  // → Upstash

    // Compute: web service (public HTTP endpoint)
    {
      "id": "api",
      "type": "web",                    // "web" | "worker" | "container" (default: "web")
      "runtime": "python",             // optional — auto-detected if omitted
      "basePath": "backend",           // directory relative to zcp.json location
      "start": "gunicorn app:app --bind 0.0.0.0:5001 --workers 2 --chdir /app",
      "port": 5001,
      "scaling": { "min": 1, "max": 3 },
      "env": [
        { "name": "DATABASE_URL", "fromService": { "id": "maindb", "value": "dbConnectionString" } },
        { "name": "REDIS_URL",    "fromService": { "id": "cache",  "value": "connectionString"  } },
        { "name": "FLASK_ENV",    "value": "production" }
      ]
    },

    // Compute: worker service (no HTTP, blocking subprocess)
    {
      "id": "temporal-worker",
      "type": "worker",
      "runtime": "python",
      "basePath": ".",
      "start": "python -m apps.workflows.worker",
      "scaling": { "min": 1, "max": 1 }
    },

    // Container: pre-built image from registry (no source code needed)
    {
      "id": "kratos",
      "type": "container",
      "image": "oryd/kratos:v1.3.1",        // registry image reference
      "command": "serve --config /etc/config/kratos/kratos.yml",  // Docker CMD (appended to image ENTRYPOINT)
      "port": 4433,                          // omit for worker-style containers
      "configFiles": {                       // baked into image at build time (optional)
        "/etc/config/kratos/kratos.yml": "kratos/kratos.yml"  // container path → local path
      },
      "scaling": { "min": 1, "max": 1 },
      "env": [
        { "name": "DSN", "fromService": { "id": "maindb", "value": "connectionString" } },
        { "name": "LOG_LEVEL", "value": "info" }
      ]
    }
  ]
}
```

### `fromService` output fields

Both infra types expose `connectionString` as the primary field. All values are strings.

| Service type | `value` field | Description |
|--------------|--------------|-------------|
| `postgres` | `connectionString` | Neon connection URI (`postgresql://...`) |
| `postgres` | `project_id` | Neon project ID |
| `postgres` | `database_name` | Neon database name |
| `redis` | `connectionString` | `rediss://:<password>@<endpoint>:<port>` |
| `redis` | `host` | Upstash endpoint hostname |
| `redis` | `port` | Port (as string) |
| `redis` | `authToken` | Upstash password |
| `redis` | `restToken` | Upstash REST API token |

---

## Theme System

Templates use a CSS custom-property theme system defined in `templates/_theme.html`.

- **4 themes:** `dark-tech` (emerald), `light-clean` (indigo), `midnight` (violet), `carbon` (orange)
- **Switching:** 4 colored dots in the nav; selection persisted to `localStorage`
- **Semantic classes:** `.card`, `.card-flush`, `.btn-primary`, `.btn-sm`, `.input-field`, `.textarea-field`, `.select-field`, `.badge-*`, `.code-chip`, `.code-block`, `.alert-error`, `.nav-link`, `.nav-link-accent`
- **Rule:** Tailwind is used for layout/spacing only. All colors go through CSS vars.

---

## Django Admin

URL: `/admin/` — branding: "Zamp Control Plane" / "ZCP Admin" / "Internal Operations"

Registered models with search + filters:
- `Organization` — search: name, slug
- `User` — search: email, username; filter: is_staff, is_active
- `ResourceAccessMapping` — search: user email, org slug; filter: role
- `NeonDatabase` — search: org slug, project_id, database_name; filter: status
- `APIKey` — search: user email, name; filter: is_active

---

## Running Locally

```bash
# Install deps (both backend and CLI)
uv sync --all-packages

# All backend commands run from zcp-backend/
cd zcp-backend

# Migrate
uv run python manage.py migrate

# Create superuser
uv run python manage.py createsuperuser

# Start Temporal worker (separate terminal, from zcp-backend/)
uv run python -m apps.workflows.worker

# Start dev server (from zcp-backend/)
uv run python manage.py runserver 8000

# Deploy via CLI (thin client → server-side orchestration)
# 1. Copy API token from dashboard
# 2. Login:
uv run zcp login --token zcp_... --api-url http://localhost:8000
# 3. Deploy (from anywhere):
uv run zcp deploy --file zcp-backend/Sample\ Deployment/zcp.json --org-slug my-org
```

---

## Environment Variables (`.env`)

```
SECRET_KEY=...
DEBUG=True
TEMPORAL_HOST=zcp-raghav.dkqth.tmprl.cloud:7233
TEMPORAL_NAMESPACE=zcp-raghav.dkqth
TEMPORAL_API_KEY=<key>
NEON_API_KEY=<key from Neon console → Account → API keys>
NEON_ORG_ID=<org ID from Neon console → Settings → General>
UPSTASH_EMAIL=<your Upstash account email>
UPSTASH_API_KEY=<key from Upstash console → Account → API keys>
SAMPLE_REPO_URL=https://github.com/sarafraghav/test_tictac.git
SAMPLE_REPO_BRANCH=main
SAMPLE_REPO_COMMIT=080d9fa6f8a2bb4cc4cab20da4358e9a00505edf
FLY_API_KEY=<Fly.io API token for container service deployments>
```

---

## Standing Instructions

- **Always test all three layers** (Django check, Temporal workflow, browser) before responding.
- **No volumes** — `apps/volumes` deleted; source is baked into Modal images via `add_local_dir`. Never re-introduce volumes.
- **Never delete `db.sqlite3`** — use additive migrations only. Only reset if absolutely necessary and explicitly confirmed.
- **Password security** — never pass passwords to Temporal. Create the user in Django before starting the workflow. Use `request.session["pending_signup_user_id"]` to carry the user identity into `WorkflowStatusView` for auto-login.
- **Logout uses a POST form** — Django 5 dropped GET logout support; `base.html` uses `<form method="post">` with CSRF token, not an `<a>` tag.
- **After signup completes**, auto-login the user and redirect to `/dashboard/` — never leave them on the status page.
- **SQL queries are SELECT-only** — `QueryDatabaseView` rejects any statement whose first keyword is not `SELECT`.
- **App name for Modal operations** — always read from `org.deployed_app.app_name`, never hardcode.
