# Production Deployment — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when deploying, debugging production, or managing VPS infrastructure.

## Server Details

| Item | Value |
|------|-------|
| **Host** | `187.124.74.175` (Hostinger, Ubuntu 24.04, 4 vCPU, 16GB RAM, 193GB disk) |
| **Domain** | `neuraleads.ai` (was `ra.partnerwithus.tech` — 301-redirects to it; see "Domain cutover" below) |
| **SSL** | Let's Encrypt (auto-renews via `certbot.timer`) |
| **SSH** | `root@187.124.74.175` (password auth — see `~/.ssh/habib-hostinger/secrets.txt`) |
| **Linux user** | `ra-user` (runs app services) |
| **App directory** | `/opt/exzelon-ra-agent/` |
| **Git branch** | `master` (single branch) |
| **GitHub repo** | `sdasgarali/exzelon_ra_agent` |

## Services

| Service | Unit Name | Port | Command | Notes |
|---------|-----------|------|---------|-------|
| Backend API | `exzelon-api` | 127.0.0.1:8000 | `systemctl restart exzelon-api` | 4 uvicorn workers, logs to journald |
| Frontend | `exzelon-web` | 3000 | `systemctl restart exzelon-web` | Next.js production, logs to journald |
| Reverse Proxy | `nginx` | 80/443 | `systemctl reload nginx` | SSL termination, security headers |
| Database | `mysql` | 3306 | `systemctl restart mysql` | User: `ra_user`, DB: `exzelon_ra_agent` |
| Cache | `redis-server` | 6379 | `systemctl restart redis-server` | Rate limits, token blacklist, ops heartbeat + alert de-dup (all degrade gracefully without it) |

## Directory Layout (VPS)

```
/opt/exzelon-ra-agent/
├── backend/
│   ├── .env                  # Backend config (DB creds, API keys, secrets)
│   ├── venv/                 # Python 3.11 virtual environment
│   ├── app/                  # FastAPI application
│   └── requirements.txt
├── frontend/
│   ├── .env.local            # NEXT_PUBLIC_API_URL (NOT in git — must exist)
│   ├── .next/                # Build output
│   └── node_modules/
├── backups/                  # pre-deploy-<ts>.sql.gz (deploy.sh, newest 10) + older pre-migrate dumps
│                             # (daily dumps: backend/data/backups/, ops state: backend/data/ops/)
├── deploy/
│   ├── deploy.sh             # Self-contained deployment script
│   ├── restore_drill.sh      # Restore newest dump into scratch DB + row-count report
│   ├── DR_RUNBOOK.md         # Backups, B2 off-site, alerts, restore, drill log
│   ├── watchdog/             # neuraleads-watchdog.{sh,service,timer}
│   ├── nginx.conf            # Nginx config template
│   ├── vps_ssh.sh            # SSH helper for non-interactive access
│   └── systemd/
│       ├── exzelon-api.service
│       └── exzelon-web.service
└── scripts/                  # Migration and utility scripts
```

## Deploy Steps (Automated)

```bash
# On VPS directly:
bash /opt/exzelon-ra-agent/deploy/deploy.sh

# From local machine via SSH:
./deploy/vps_ssh.sh "bash /opt/exzelon-ra-agent/deploy/deploy.sh"
```

The script performs: **pre-deploy DB dump** (aborts on failure) -> git pull -> pip install ->
npm build -> **`alembic upgrade head`** (aborts before restart on failure) -> restart services ->
**wait up to 60s for `/health`** -> print `/api/v1/ready` JSON -> print rollback commands
(previous SHA + `gunzip -c <dump> | mysql exzelon_ra_agent`). Overrides: `DEPLOY_DB_NAME`,
`PREDEPLOY_BACKUP_DIR`, `PREDEPLOY_KEEP` (10), `HEALTH_WAIT_SECONDS` (60).

## Readiness, watchdog & alerts (launch readiness M1-M4)

- `GET /api/v1/ready` (also `/ready` on :8000; nginx only proxies `/api/` + `/health`, so use the
  `/api/v1` path externally): DB, Redis (non-critical), scheduler heartbeat <= 10 min, disk free,
  newest local backup <= 26h. 200 / 503 + per-check JSON. `/health` unchanged.
- Scheduler heartbeat: `job_scheduler_heartbeat` (every minute, scheduler-owning worker) writes
  Redis key `neuraleads:ops:scheduler_heartbeat` + file `backend/data/ops/scheduler_heartbeat`.
- Alerts: `app/services/alerting.py` `send_alert(kind, ...)` -> `ALERT_EMAIL` (info@neuraleads.ai)
  via the global Resend/SMTP system mailer, max 1 per kind per `ALERT_MIN_INTERVAL_MINUTES`.
  Kinds: `unhandled_exception`, `backup_failed`, `backup_offsite_failed`. CLI:
  `cd backend && venv/bin/python -m app.services.alerting send --subject S --body B [--no-dedup]`.
- Watchdog: `deploy/watchdog/neuraleads-watchdog.{sh,service,timer}` (every 5 min; 2 failures ->
  one DOWN email, one RECOVERED email). Install steps in `deploy/DR_RUNBOOK.md`.
- Backups / B2 off-site / restore drill (`deploy/restore_drill.sh`): see `deploy/DR_RUNBOOK.md`.

## Deploy Steps (Manual)

```bash
# 1. Pull latest code
cd /opt/exzelon-ra-agent && git pull origin master

# 2. Backend: install deps
cd /opt/exzelon-ra-agent/backend && source venv/bin/activate && pip install -r requirements.txt

# 3. Frontend: rebuild
cd /opt/exzelon-ra-agent/frontend && npm run build

# 4. Restart services
systemctl restart exzelon-api exzelon-web

# 5. Verify
systemctl status exzelon-api exzelon-web
curl -s https://neuraleads.ai/health
```

## Critical: Frontend `.env.local`

The frontend **requires** `/opt/exzelon-ra-agent/frontend/.env.local` with:
```
NEXT_PUBLIC_API_URL=https://neuraleads.ai/api/v1
```
Without this, `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000/api/v1`, which works for SSR but fails for browser-side API calls. This file is **NOT in git** — the deploy script auto-creates it if missing.

## Backend `.env` keys added 2026-10-12 (credit loopholes)

Add to `/opt/exzelon-ra-agent/backend/.env` before deploying `bugfix/credit-loopholes`:

| Key | Prod value | Why |
|---|---|---|
| `RATE_LIMIT_STORAGE_URI` | `redis://localhost:6379/1` | Shares rate limits across the uvicorn workers; empty = per-process memory (limits multiply by worker count) |
| `MAX_DAILY_SEND_LIMIT_PER_MAILBOX` | `50` | Upper bound on any mailbox/tenant daily send limit |
| `MAX_IMPORT_ROWS` | `5000` | Row cap for CSV / Google-Sheet imports |
| `BLOCKED_SIGNUP_DOMAINS` | *(optional)* | Extra disposable domains to block at signup |

No schema change. `CREDIT_ENFORCEMENT_ENABLED` is untouched (still opt-in).

## Database Migrations

**Alembic is live on prod** (stamped `0001_baseline` and upgraded to `0004` on 2026-09-23).
The legacy idempotent block in `main.py`'s lifespan still runs on startup as a safety net
(see `deploy/MIGRATIONS.md`); every NEW schema change is an Alembic revision.

**Since launch-readiness M5, `deploy.sh` takes the backup and runs Alembic itself** (in the
order below). The manual sequence is kept for reference / hand deploys (the old code keeps
serving until the restart, and it cannot read a migrated schema, so migrate and restart
back-to-back):

```bash
cd /opt/exzelon-ra-agent && git pull --ff-only origin master
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm run build
# 1. backup  (ra_user lacks PROCESS -> --no-tablespaces)
mysqldump --single-transaction --no-tablespaces --routines --triggers exzelon_ra_agent | gzip > /opt/exzelon-ra-agent/backups/pre-migrate-$(date +%Y%m%d-%H%M%S).sql.gz
# 2. migrate  (DATABASE_URL from settings)
cd ../backend && alembic upgrade head && alembic current
# 3. restart immediately
systemctl restart exzelon-api exzelon-web
```

Backups live in `/opt/exzelon-ra-agent/backups/` (e.g. `pre-migrate-20260923-125816.sql.gz`).
Rollback = restore the dump, `git checkout <previous>`, rebuild, restart.

Known pre-existing startup noise: `demo_seeder` logs "Failed to seed demo data" (duplicate
`client_info` for tenant 2) on every worker start — harmless, not a deploy failure.

## Systemd Service Files

Version-controlled in `deploy/systemd/`. To install or update on VPS:
```bash
cp /opt/exzelon-ra-agent/deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart exzelon-api exzelon-web
```
**`exzelon-api` binds uvicorn to `127.0.0.1:8000`** (launch readiness M6, was `0.0.0.0`) —
nginx's `api_backend` upstream and the MCP server already use `127.0.0.1:8000`; ufw also
blocks 8000. `deploy.sh` does NOT copy unit files: after pulling a change to
`deploy/systemd/*`, run the three commands above (verify with `ss -tlnp | grep 8000` →
`127.0.0.1:8000`).

## Nginx Config

Template in `deploy/nginx.conf` (live file: `/etc/nginx/sites-enabled/ra-app`). To update on VPS:
```bash
cp /opt/exzelon-ra-agent/deploy/nginx.conf /etc/nginx/sites-available/ra-app
sed -i 's/YOUR_DOMAIN/neuraleads.ai/g' /etc/nginx/sites-available/ra-app
nginx -t && systemctl reload nginx
```

**Caching (2026-08-17):** `location /` sends `Cache-Control: no-cache` on the HTML shell
(via `proxy_hide_header Cache-Control` + `add_header`) so a new frontend deploy is picked
up on the next normal reload — no hard refresh needed. Hashed assets under `/_next/static/`
stay `public, immutable`. Because any `add_header` in a location cancels inheritance of the
server-level `add_header`s, the 5 security headers are re-declared inside `location /`.
**Gotcha:** never leave config backups in `sites-enabled/` — nginx `include`s `*`, so a
`ra-app.bak` there causes `duplicate upstream` and `nginx -t` fails. Keep backups in
`/root/nginx-backups/`.

## MCP connector (hosted `/mcp`) — LIVE since 2026-10-07 (master 21ed0d5)

Optional service for AI tools; see `CLAUDE_REFERENCE/mcp-connector.md`.

| Item | Value |
|---|---|
| Code | `/opt/exzelon-ra-agent/mcp_server/` (own venv `.venv`, Python 3.11+) |
| Service | `neuraleads-mcp` (`deploy/systemd/neuraleads-mcp.service`), user `ra-user` |
| Port | **8010**, loopback only. Verify free first: `ss -tlnp \| grep :8010` |
| Env | `/opt/exzelon-ra-agent/mcp_server/.env` (API URL `http://127.0.0.1:8000/api/v1`, port, `MCP_ALLOWED_HOSTS`). Holds no API keys. |
| Nginx | include `deploy/mcp/nginx-mcp-location.conf` (`location = /mcp`) in the neuraleads.ai 443 block, `nginx -t`, reload |
| Install/update | `bash /opt/exzelon-ra-agent/deploy/mcp/install_mcp.sh` (idempotent; health-checks `/healthz`) |
| Logs | `journalctl -u neuraleads-mcp -f` |
| Smoke test | `curl -s -X POST https://neuraleads.ai/mcp -H "Authorization: Bearer <key>" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'` |

Installed 2026-10-07: venv + `.env` created by the script; nginx include added before `location /api/` in
`/etc/nginx/sites-enabled/ra-app` (backup `/root/nginx-backups/ra-app.bak-20261007-152343`). Port 8010 is in
the global VPS port table. Rollback: `systemctl disable --now neuraleads-mcp`, restore the nginx backup, reload.

Note: `deploy.sh` health check can report 502 for ~15s after restart while the 4 uvicorn workers start;
re-check `/health` before treating it as a failure.

## Viewing Logs

```bash
journalctl -u exzelon-api -f              # Backend logs (live)
journalctl -u exzelon-web -f              # Frontend logs (live)
journalctl -u exzelon-api --since "1h ago" # Last hour
journalctl -u nginx -f                    # Nginx access/error
```

## SSH Access from Local Machine

Auth is via the **passphrase-less deploy key** `~/.ssh/id_ed25519_deploy` (already
authorized on the VPS). The old root password was rotated and is now rejected — do
not use password/askpass auth.

```bash
# Autonomous SSH (deploy key, no prompts):
ssh -i ~/.ssh/id_ed25519_deploy -o IdentitiesOnly=yes root@187.124.74.175 "command"

# Using the helper script (recommended — uses the deploy key, BatchMode, no prompts):
./deploy/vps_ssh.sh "command to run on VPS"

# Override key/host without editing the script:
VPS_SSH_KEY=~/.ssh/other_key VPS_HOST=root@1.2.3.4 ./deploy/vps_ssh.sh "command"
```

## Rollback

```bash
cd /opt/exzelon-ra-agent
git log --oneline -10           # Find the commit to rollback to
git checkout <commit-hash>      # Detached HEAD at that commit
cd frontend && npm run build
systemctl restart exzelon-api exzelon-web
```

## Domain cutover: ra.partnerwithus.tech -> neuraleads.ai

**Done 2026-09-25.** Prod env keys live in the ROOT `/opt/exzelon-ra-agent/.env` with the `PROD_`
prefix (`PROD_BASE_URL`, `PROD_CORS_ORIGINS`); `backend/.env` holds only a few unprefixed keys.
The DB setting `warmup_tracking_base_url` also stores the host. `MS365_OAUTH_REDIRECT_URI` intentionally
still points at the old host until the new URI is registered in Azure (the 301 preserves the query string).
certbot has two ACME accounts on the box: pass `--account` taken from an existing renewal conf.

Emails build links from `BASE_URL` alone (`settings.EFFECTIVE_FRONTEND_URL`), so the host
change is config-only after the code change. Steps on the VPS:

1. **DNS (Cloudflare, zone neuraleads.ai):** A `@` -> 187.124.74.175 and A `www` -> 187.124.74.175,
   both **DNS-only (grey cloud)** so certbot's HTTP-01 challenge reaches nginx.
   Check: `dig +short neuraleads.ai @1.1.1.1` returns 187.124.74.175.
2. **Backup:** `cp /etc/nginx/sites-available/ra-app /root/nginx-backups/ra-app.bak-<ts>`, `cp backend/.env{,.bak-<ts>}`,
   `cp frontend/.env.local{,.bak-<ts>}`.
3. **nginx:** in the ra-app site set `server_name neuraleads.ai www.neuraleads.ai;`, then
   `certbot --nginx -d neuraleads.ai -d www.neuraleads.ai`. Add a separate server block for
   `ra.partnerwithus.tech` (keep its existing cert) that does `return 301 https://neuraleads.ai$request_uri;`.
   Add a `www` -> apex 301 too. `nginx -t && systemctl reload nginx`.
4. **backend/.env:** `BASE_URL=https://neuraleads.ai`; add `https://neuraleads.ai,https://www.neuraleads.ai`
   to `CORS_ORIGINS` (keep the old origin until the redirect is verified); update
   `MS365_OAUTH_REDIRECT_URI` and any Google OAuth redirect URI to the new host.
5. **frontend/.env.local:** `NEXT_PUBLIC_API_URL=https://neuraleads.ai/api/v1` (+ `NEXT_PUBLIC_SITE_URL`
   if set). These are baked in at build time -> `npm run build`.
6. `systemctl restart exzelon-api exzelon-web`; check `curl -fsS https://neuraleads.ai/health`
   and `curl -sI https://ra.partnerwithus.tech/login` (expect 301 -> neuraleads.ai/login).
7. **External consoles (manual):** add the new redirect URIs in Azure (MS365 app) and Google Cloud
   OAuth clients, and the new webhook URL in Stripe once Stripe is set up.

Rollback: restore the three `.bak-<ts>` files, rebuild frontend, restart services, reload nginx.
