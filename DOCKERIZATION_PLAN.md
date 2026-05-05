# Dockerization Plan — Menu Zen Backend

A complete checklist of everything needed to containerize this FastAPI project so it can run anywhere with no host-level constraints.

**Database decision: PostgreSQL in production (and in dev too — same engine in both environments avoids dialect-divergence bugs).**

---

## 1. Project Snapshot (what we're packaging)

| Item | Value |
|---|---|
| Framework | FastAPI 0.116 + Uvicorn 0.35 |
| Language | Python 3.13 (current local) — pin to **3.12-slim** in Docker for stability |
| ASGI entrypoint | `app.main:app` |
| Runtime port | `8000` |
| Database (current) | SQLite file `database.db` at project root — **to be replaced by Postgres** |
| Database (target) | PostgreSQL 16 |
| Migrations | Alembic (`alembic/` + `alembic.ini`) |
| Static / user files | `uploads/` (mounted at `/uploads`) |
| Realtime | WebSockets (`app/routers/ws_connect.py`) |
| Secrets / config | `.env` (SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, SUPER_ADMIN_*, DATABASE_URL) |
| Startup side-effects | `create_db_and_tables()` + RBAC + super-admin seeding in `lifespan` |

---

## 2. Files to Create

### 2.1 `Dockerfile` (multi-stage, slim, non-root)
- **Base:** `python:3.12-slim`
- **Stage 1 — builder:** install build deps (`build-essential`, `libpq-dev`), create venv, `pip install --no-cache-dir -r requirements.txt`.
- **Stage 2 — runtime:** install only `libpq5` (the Postgres client lib needed at runtime), copy venv from builder, copy app source, drop privileges to `appuser`, `EXPOSE 8000`.
- **CMD:** entrypoint script that runs migrations then launches uvicorn (see 2.3).
- Use `.dockerignore` aggressively.

> Alternative: use `psycopg[binary]` (bundled C extension) and skip `libpq-dev` / `libpq5` entirely. Simpler image but not recommended for hot prod paths. **Going with `psycopg[binary]` for v1** — easier and "fast everywhere" matches the user's portability goal.

### 2.2 `.dockerignore`
```
.git
.venv
venv
__pycache__
*.pyc
*.pyo
build/
dist/
*.spec
database.db
database.db.backup_*
.env
.env.*
uploads/                # bind-mounted at runtime, not baked in
tests/
*.md
.vscode/
.idea/
.DS_Store
```

### 2.3 `entrypoint.sh`
```sh
#!/bin/sh
set -e
# Wait for Postgres (compose's depends_on/healthcheck handles this, but
# belt-and-braces in case the script is run outside compose).
echo "Running database migrations..."
alembic upgrade head
echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
```
Make it executable (`chmod +x entrypoint.sh`) and `COPY` it into the image.

> The `lifespan` in [app/main.py:240](app/main.py#L240) currently calls `create_db_and_tables()` — keep it as a safety net, but Alembic via the entrypoint becomes the source of truth for schema.

### 2.4 `docker-compose.yml`
```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"          # HTTP/3
    environment:
      DOMAIN: ${DOMAIN}
      ACME_EMAIL: ${ACME_EMAIL}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data        # certificates — survive restarts (don't wipe!)
      - caddy_config:/config
    depends_on:
      - api
    restart: unless-stopped

  api:
    build: .
    expose: ["8000"]            # internal only — Caddy reaches it via the compose network
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./uploads:/app/uploads
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

volumes:
  pgdata:
  caddy_data:
  caddy_config:
```
Neither the DB nor the API is exposed to the host in production — Caddy is the only public surface, and it terminates TLS for both HTTP and WebSocket traffic. The dev `docker-compose.override.yml` re-publishes `8000` and `5432` for local work.

### 2.5 `docker-compose.override.yml` (dev-only, auto-loaded)

By default, source code is **baked into the image at build time** — local edits don't appear in the running container until rebuild. That's correct for production but painful for development. Compose auto-merges `docker-compose.override.yml` whenever you run plain `docker compose ...`, so we use it to bind-mount source and enable hot-reload:

```yaml
services:
  api:
    ports: ["8000:8000"]         # bypass Caddy locally — hit the API directly
    volumes:
      - ./app:/app/app           # live source mount — edit on host, container sees it
      - ./alembic:/app/alembic   # so new migrations show up without rebuild
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      SQL_ECHO: "true"
  db:
    ports: ["5432:5432"]         # expose DB to host for local debugging (psql, GUI clients)
  caddy:
    profiles: ["disabled"]       # don't start Caddy in dev — no certs, no domain locally
```

**Key rule:** keep this file out of production deploys. On the server, run `docker compose -f docker-compose.yml up -d --build` to skip the override.

#### When does Docker pick up changes?

| Action | Auto-reflected? | What to run |
|---|---|---|
| Edit a `.py` file | Yes — uvicorn `--reload` watches files | nothing |
| Add a new file under `app/` | Yes | nothing |
| Add a dependency to `requirements.txt` | No | `docker compose up -d --build` |
| Change `Dockerfile` / `entrypoint.sh` | No | `docker compose up -d --build` |
| Generate a new Alembic migration | Live (mounted) | `docker compose exec api alembic revision --autogenerate -m "..."` |
| Apply Alembic migrations | Live | `docker compose exec api alembic upgrade head` (or just restart — entrypoint runs it) |
| Edit `.env` | No (env vars read at process start) | `docker compose up -d` (recreates container) |
| Production deploy | Always rebuilt | `docker compose -f docker-compose.yml up -d --build` |

> The bind mount overlays the image's `/app/app` directory, so the `COPY` in the Dockerfile is shadowed by your host files. In production, no override file → no shadow → the immutable image is what runs.

### 2.6 `.env.example`
```
# App
SECRET_KEY=change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=3000

# Super admin (used once on first startup; password rotation enforced)
SUPER_ADMIN_EMAIL=
SUPER_ADMIN_USERNAME=super_admin
SUPER_ADMIN_PASSWORD=

# Postgres (consumed by the db service AND interpolated into DATABASE_URL)
POSTGRES_USER=menuzen
POSTGRES_PASSWORD=change-me
POSTGRES_DB=menuzen

# CORS — comma-separated origins (no wildcards in prod when credentials are on)
CORS_ORIGINS=http://localhost:5173

# Caddy / TLS (production only — leave blank in dev)
DOMAIN=api.example.com
ACME_EMAIL=ops@example.com

# Off-host backups (production only)
BACKUP_S3_BUCKET=                # e.g. s3://menuzen-backups (OVH Object Storage S3-compatible endpoint)
BACKUP_S3_ENDPOINT=              # e.g. https://s3.gra.io.cloud.ovh.net
BACKUP_S3_ACCESS_KEY=
BACKUP_S3_SECRET_KEY=
BACKUP_RETENTION_DAYS=14
```

### 2.7 `Caddyfile` (TLS terminator + reverse proxy)

Caddy auto-provisions and renews Let's Encrypt certificates as long as the domain's DNS A/AAAA record points at the VPS and ports 80/443 are reachable.

```caddy
{$DOMAIN} {
    encode zstd gzip

    # WebSocket route (FastAPI ws_connect.py)
    @ws {
        header Connection *Upgrade*
        header Upgrade    websocket
    }
    reverse_proxy @ws api:8000

    # Static uploads — served directly by FastAPI's StaticFiles mount
    reverse_proxy /uploads/* api:8000

    # Everything else
    reverse_proxy api:8000 {
        header_up X-Real-IP        {remote_host}
        header_up X-Forwarded-For  {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # Basic security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options    "nosniff"
        Referrer-Policy           "strict-origin-when-cross-origin"
        -Server
    }

    # ACME contact for Let's Encrypt
    tls {$ACME_EMAIL}
}
```

**DNS prerequisite:** before the first `up`, point `${DOMAIN}` at the VPS's public IP. Caddy will fail certificate issuance otherwise (it'll keep retrying — check `docker compose logs caddy`).

**Local dev:** the override file disables Caddy via `profiles: ["disabled"]` ([Section 2.5](#25-docker-composeoverrideyml-dev-only-auto-loaded)), so you hit the API directly on `:8000` without TLS. No certs are issued for `localhost`.

### 2.8 `scripts/backup.sh` (off-host Postgres dump → S3-compatible storage)

OVH Object Storage exposes an S3-compatible endpoint, so any S3 client works (`aws-cli`, `mc`, `rclone`). This script runs on the **host** via cron, calls `pg_dump` inside the `db` container, gzips, and uploads. If the VPS dies, the dumps survive in object storage.

```sh
#!/bin/sh
set -eu

# Loaded from the project's .env (same vars as compose)
PROJECT_DIR="/opt/menu_zen_back"      # adjust to your VPS deploy path
cd "$PROJECT_DIR"
. ./.env

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMPFILE="/tmp/menuzen_${STAMP}.sql.gz"
S3_KEY="postgres/menuzen_${STAMP}.sql.gz"

# 1. Dump from the running container (no host-side psql/pg_dump needed)
docker compose -f docker-compose.yml exec -T db \
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --clean \
    | gzip -9 > "${TMPFILE}"

# 2. Upload via aws-cli (configured to point at OVH's S3-compatible endpoint)
AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
aws --endpoint-url "${BACKUP_S3_ENDPOINT}" \
    s3 cp "${TMPFILE}" "${BACKUP_S3_BUCKET}/${S3_KEY}"

# 3. Cleanup local tmp
rm -f "${TMPFILE}"

# 4. Prune remote dumps older than retention window
CUTOFF=$(date -u -d "-${BACKUP_RETENTION_DAYS} days" +%Y-%m-%d 2>/dev/null \
       || date -u -v-"${BACKUP_RETENTION_DAYS}"d +%Y-%m-%d)
AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY}" \
AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_KEY}" \
aws --endpoint-url "${BACKUP_S3_ENDPOINT}" \
    s3 ls "${BACKUP_S3_BUCKET}/postgres/" \
    | awk -v cutoff="${CUTOFF}" '$1 < cutoff {print $4}' \
    | while read -r OLD; do
        [ -n "${OLD}" ] && aws --endpoint-url "${BACKUP_S3_ENDPOINT}" \
            s3 rm "${BACKUP_S3_BUCKET}/postgres/${OLD}"
      done

echo "Backup ${S3_KEY} uploaded."
```

**Install on the VPS once:**

```bash
# 1. Install the AWS CLI (host, not container)
sudo apt-get install -y awscli   # or: pipx install awscli

# 2. Make the script executable
chmod +x /opt/menu_zen_back/scripts/backup.sh

# 3. Add to root's crontab — daily at 03:17 UTC
(sudo crontab -l 2>/dev/null; echo "17 3 * * * /opt/menu_zen_back/scripts/backup.sh >> /var/log/menuzen-backup.log 2>&1") | sudo crontab -
```

**Restore drill (do this once, before you need it):**

```bash
# Pull a backup down
aws --endpoint-url "${BACKUP_S3_ENDPOINT}" s3 cp \
    "${BACKUP_S3_BUCKET}/postgres/menuzen_<stamp>.sql.gz" /tmp/restore.sql.gz

# Pipe into the running db container
gunzip -c /tmp/restore.sql.gz | docker compose exec -T db \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
```

> **Why uploads are not yet in this backup:** the `./uploads` bind mount sits on the same VPS disk as `pgdata`. If you keep important user-uploaded files, extend the script with `tar czf - uploads | aws s3 cp - "${BACKUP_S3_BUCKET}/uploads/uploads_${STAMP}.tar.gz"`. Skipped in v1 to keep the script focused.

---

## 3. Code Changes Required

### 3.1 Add Postgres driver to `requirements.txt`
```
psycopg[binary]==3.2.3
```
Keep the rest unchanged.

### 3.2 Make the DB URL configurable — [app/configs/database_configs.py](app/configs/database_configs.py)
Currently lines 6–10 hard-code SQLite. Replace with:
```python
import os
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://menuzen:menuzen@localhost:5432/menuzen")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False, pool_pre_ping=True)
```
- Removes hard-coded `sqlite:///`.
- `echo=True` → `False` (or env-driven via `SQL_ECHO`); current `True` floods container logs.
- `pool_pre_ping=True` recovers gracefully from killed Postgres connections (e.g., DB restart).

### 3.3 Wire Alembic to `DATABASE_URL` — [alembic/env.py](alembic/env.py)
Inside `run_migrations_online()` (and offline), override the URL from env before constructing the engine:
```python
import os
url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", url)
```
Place this near the top of `env.py`, after `config = context.config`. Then both online and offline modes pick up the env var automatically.

### 3.4 Make `render_as_batch` conditional — [alembic/env.py:82](alembic/env.py#L82)
`render_as_batch=True` is a SQLite workaround for missing `ALTER COLUMN`. On Postgres it's unneeded and slightly slower. Set:
```python
render_as_batch=url.startswith("sqlite"),
```

### 3.5 Tighten CORS — [app/main.py:259](app/main.py#L259)
`allow_origins=["*"]` with `allow_credentials=True` is invalid per the CORS spec and rejected by browsers. Replace with:
```python
import os
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=bool(origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3.6 Optional: drop `set_sqlite_pragma` listener — [alembic/env.py:30](alembic/env.py#L30)
Harmless on Postgres (the `'sqlite' in str(dbapi_conn)` check makes it a no-op), so leaving it is fine. Remove only if you want a clean cut.

---

## 4. Database Bootstrap & Future Data Migration

**v1 strategy: fresh start.** Bring up an empty Postgres, let Alembic build the schema, and let the `lifespan` seeders in [app/main.py:240](app/main.py#L240) create the RBAC roles/permissions + super admin from `.env`. No existing data is carried over.

**Later (when the new stack is verified):** migrate the old SQLite data with [`pgloader`](https://pgloader.io/):
```
pgloader sqlite:///path/to/database.db postgresql://menuzen:pass@localhost:5432/menuzen
```
Run this against the **already-migrated** Postgres schema (so structure exists). Truncate the seeded RBAC/super-admin rows first if pgloader complains about PK conflicts.

Keep `database.db` and `database.db.backup_20260428_163221` on the host (already excluded from the image via `.dockerignore`) until the migration is done and verified.

---

## 5. Volumes & Persistence

| Path | Purpose | Mount |
|---|---|---|
| `pgdata` (named volume) → `/var/lib/postgresql/data` | Postgres data files | named volume |
| `caddy_data` (named volume) → `/data` | Let's Encrypt certs + ACME account key — **never wipe** | named volume |
| `caddy_config` (named volume) → `/config` | Caddy autosaved config | named volume |
| `./uploads` (bind) → `/app/uploads` | User-uploaded files served at `/uploads` | bind mount |
| `./Caddyfile` (bind) → `/etc/caddy/Caddyfile` | Reverse-proxy config | bind mount, read-only |

Anything not mounted is wiped on rebuild. Named volumes survive `docker compose down`; they die only on `docker compose down -v` — which would also delete your TLS certs and trigger Let's Encrypt rate limits if done carelessly.

**Backups:** see [Section 2.8](#28-scriptsbackupsh-off-host-postgres-dump--s3-compatible-storage) for the off-host script (daily `pg_dump` → OVH Object Storage with retention pruning). For ad-hoc local dumps:
```bash
docker compose exec db pg_dump -U menuzen menuzen > backup.sql
```

---

## 6. Networking & Reverse Proxy

- **Caddy** is the only public-facing service in production. It owns ports `80`, `443`, and `443/udp` (HTTP/3) and proxies to `api:8000` over the internal compose network.
- The `api` container uses `expose: ["8000"]` (not `ports:`) — reachable from Caddy, invisible to the host. The `db` container is the same.
- TLS certificates are issued automatically by Let's Encrypt on first request to `${DOMAIN}`. Renewal is handled by Caddy in the background — no cron needed.
- WebSocket route in [app/routers/ws_connect.py](app/routers/ws_connect.py): the `@ws` matcher in the [Caddyfile](#27-caddyfile-tls-terminator--reverse-proxy) forwards `Upgrade`/`Connection` headers; `--proxy-headers` in the entrypoint makes uvicorn trust `X-Forwarded-*`.
- **OVH firewall** (host level, separate from Docker): allow `22/tcp` (SSH), `80/tcp`, `443/tcp`, `443/udp`. Block everything else, including `8000` and `5432`. With `ufw`:
  ```bash
  sudo ufw default deny incoming
  sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443
  sudo ufw enable
  ```

---

## 7. Security Checklist

- [ ] `.env` is **not** committed and **not** copied into the image.
- [ ] Container runs as non-root `appuser`.
- [ ] `SECRET_KEY` is strong random (not the `fallback-secret-key` in [app/configs/auth_configs.py:6](app/configs/auth_configs.py#L6)).
- [ ] `POSTGRES_PASSWORD` is strong; not the example value.
- [ ] `SUPER_ADMIN_PASSWORD` rotated after first login (`must_change_password=True` is already enforced).
- [ ] `CORS_ORIGINS` restricted (Section 3.5).
- [ ] Postgres port `5432` **not** published to host in production.
- [ ] API port `8000` uses `expose:`, not `ports:`, so only Caddy can reach it.
- [ ] OVH firewall (`ufw` or OVH control panel) only allows `22/80/443`.
- [ ] DNS A/AAAA record for `${DOMAIN}` points at the VPS public IP **before** first `compose up` (otherwise Let's Encrypt issuance fails and may rate-limit).
- [ ] `caddy_data` volume is in your backup story or you accept re-issuing certs from scratch on rebuild.
- [ ] `database.db.backup_*` excluded via `.dockerignore`.
- [ ] Off-host backup cron is installed AND a restore drill has been performed at least once.
- [ ] `BACKUP_S3_*` credentials are scoped to that one bucket, not full-account keys.
- [ ] Consider a read-only root filesystem (`read_only: true` in compose) once paths are stable.

---

## 8. Image-Size Optimisations

- `python:3.12-slim` (~50 MB) over `python:3.12` (~1 GB).
- Multi-stage build keeps build deps out of the runtime image.
- `pip install --no-cache-dir`.
- `.dockerignore` excludes `build/`, `dist/`, `*.spec` (PyInstaller artifacts).
- Consider `uv` or `pip-tools` for lockfile-based reproducible builds (later optimisation).

---

## 9. Health & Observability

- Add `GET /health` returning `{"status": "ok"}`.
- Add Docker `HEALTHCHECK` in the Dockerfile hitting `/health`.
- Sentry SDK is already in `requirements.txt` — wire `SENTRY_DSN` env var if desired.
- Structured JSON logs (optional v2): swap uvicorn's default formatter via a logging config.

---

## 10. Build & Run — Operator Cheat Sheet

```bash
# Copy env template
cp .env.example .env && $EDITOR .env

# Build and start
docker compose up -d --build

# Tail API logs
docker compose logs -f api

# Run migrations manually (rare — entrypoint does this)
docker compose exec api alembic upgrade head

# Generate a new migration after model change
docker compose exec api alembic revision --autogenerate -m "describe change"

# Open a shell in the API container
docker compose exec api /bin/sh

# Backup the database
docker compose exec db pg_dump -U menuzen menuzen > backup_$(date +%F).sql

# Restore
cat backup_2026-05-04.sql | docker compose exec -T db psql -U menuzen menuzen

# Tear down (data preserved)
docker compose down

# Tear down + wipe DB volume (DESTRUCTIVE)
docker compose down -v
```

---

## 11. Open Questions / Decisions

1. **Multi-arch image (amd64 + arm64)?** Use `docker buildx` if deploying to ARM (e.g., Raspberry Pi, AWS Graviton).
2. **CI build → registry?** GitHub Actions to build/push to GHCR or Docker Hub on tag — out of scope for v1.
3. **Single-worker uvicorn or `--workers N`?** Multiple workers + WebSockets needs sticky sessions or a pub/sub layer (Redis) for cross-worker broadcast. v1 ships with single worker.

---

## 12. Order of Operations

1. Apply code changes from Section 3 (DB URL, alembic env, CORS, requirements).
2. Write `.dockerignore`, `Dockerfile`, `entrypoint.sh`, `docker-compose.yml`, `docker-compose.override.yml`, `.env.example`, `Caddyfile`, `scripts/backup.sh`.
3. **Local dev**: `cp .env.example .env`, fill app secrets (skip `DOMAIN`/`ACME_EMAIL`/`BACKUP_*`), `docker compose up -d --build`. Caddy stays disabled by the override profile.
4. Verify locally: API at `http://localhost:8000/`, super admin login, uploads persist after `docker compose down && up`, WebSocket connects, migrations rerun cleanly.
5. Add `/health` + Docker `HEALTHCHECK` (Section 9).
6. **OVH VPS prep**: provision VPS, install Docker + Docker Compose, configure `ufw` (Section 6), point DNS at the VPS, create OVH Object Storage bucket + credentials.
7. **Production deploy**: clone repo to `/opt/menu_zen_back`, fill all env vars including TLS + backup, `docker compose -f docker-compose.yml up -d --build`. Watch `docker compose logs caddy` until cert issuance completes.
8. Install backup cron (Section 2.8) and **run a restore drill** against a throwaway DB before declaring done.
9. Tighten secrets, CORS, non-root, no exposed Postgres port (Section 7).
10. **Data migration from old SQLite** (Section 4) once the new stack is proven.
11. (Optional) Multi-arch build, CI/CD pipeline, separate staging environment.
12. Update `README.md` with the new deploy story.
