# Production Deployment — Exzelon RA Agent

> Referenced from: `CLAUDE.md` — Read this when deploying, debugging production, or managing VPS infrastructure.

## Server Details

| Item | Value |
|------|-------|
| **Host** | `187.124.74.175` (Hostinger, Ubuntu 24.04, 4 vCPU, 16GB RAM, 193GB disk) |
| **Domain** | `ra.partnerwithus.tech` |
| **SSL** | Let's Encrypt (auto-renews via `certbot.timer`) |
| **SSH** | `root@187.124.74.175` (password auth — see `~/.ssh/habib-hostinger/secrets.txt`) |
| **Linux user** | `ra-user` (runs app services) |
| **App directory** | `/opt/exzelon-ra-agent/` |
| **Git branch** | `master` (single branch) |
| **GitHub repo** | `sdasgarali/exzelon_ra_agent` |

## Services

| Service | Unit Name | Port | Command | Notes |
|---------|-----------|------|---------|-------|
| Backend API | `exzelon-api` | 8000 | `systemctl restart exzelon-api` | 4 uvicorn workers, logs to journald |
| Frontend | `exzelon-web` | 3000 | `systemctl restart exzelon-web` | Next.js production, logs to journald |
| Reverse Proxy | `nginx` | 80/443 | `systemctl reload nginx` | SSL termination, security headers |
| Database | `mysql` | 3306 | `systemctl restart mysql` | User: `ra_user`, DB: `exzelon_ra_agent` |
| Cache | `redis-server` | 6379 | `systemctl restart redis-server` | Currently unused by app (reserved) |

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
├── data/
│   └── backups/              # Database backup .sql.gz files
├── deploy/
│   ├── deploy.sh             # Self-contained deployment script
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

The script performs: git pull -> pip install -> npm build -> restart services -> health checks.

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
curl -s https://ra.partnerwithus.tech/health
```

## Critical: Frontend `.env.local`

The frontend **requires** `/opt/exzelon-ra-agent/frontend/.env.local` with:
```
NEXT_PUBLIC_API_URL=https://ra.partnerwithus.tech/api/v1
```
Without this, `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000/api/v1`, which works for SSR but fails for browser-side API calls. This file is **NOT in git** — the deploy script auto-creates it if missing.

## Database Migrations

Migrations are **auto-applied on app startup** via `main.py` lifespan hooks (ad-hoc `ALTER TABLE` statements). No Alembic yet.

After adding a new migration hook:
1. Add the migration in `backend/app/main.py` inside the `lifespan()` function
2. Deploy normally — the migration runs when `exzelon-api` restarts
3. Verify: `journalctl -u exzelon-api --since "5 min ago" | grep -i migrat`

## Systemd Service Files

Version-controlled in `deploy/systemd/`. To install or update on VPS:
```bash
cp /opt/exzelon-ra-agent/deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart exzelon-api exzelon-web
```

## Nginx Config

Template in `deploy/nginx.conf`. To update on VPS:
```bash
cp /opt/exzelon-ra-agent/deploy/nginx.conf /etc/nginx/sites-available/ra-app
sed -i 's/YOUR_DOMAIN/ra.partnerwithus.tech/g' /etc/nginx/sites-available/ra-app
nginx -t && systemctl reload nginx
```

## Viewing Logs

```bash
journalctl -u exzelon-api -f              # Backend logs (live)
journalctl -u exzelon-web -f              # Frontend logs (live)
journalctl -u exzelon-api --since "1h ago" # Last hour
journalctl -u nginx -f                    # Nginx access/error
```

## SSH Access from Local Machine

```bash
# Interactive SSH (requires password):
ssh -o PubkeyAuthentication=no root@187.124.74.175

# Non-interactive (from scripts — uses askpass):
DISPLAY=:0 SSH_ASKPASS=/tmp/vps_askpass.sh ssh -o PubkeyAuthentication=no root@187.124.74.175 "command" < /dev/null

# Using the helper script:
./deploy/vps_ssh.sh "command to run on VPS"
```

## Rollback

```bash
cd /opt/exzelon-ra-agent
git log --oneline -10           # Find the commit to rollback to
git checkout <commit-hash>      # Detached HEAD at that commit
cd frontend && npm run build
systemctl restart exzelon-api exzelon-web
```
