# Deployment Guide � NeuraLeads AI Agent

> **Last updated:** 2026-02-28

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Local Development Setup](#2-local-development-setup)
3. [Docker Development](#3-docker-development)
4. [Production Deployment](#4-production-deployment)
5. [Environment Variables Reference](#5-environment-variables-reference)
6. [Database Migrations](#6-database-migrations)
7. [SSL/TLS with Nginx Reverse Proxy](#7-ssltls-with-nginx-reverse-proxy)
8. [Backup Strategy](#8-backup-strategy)
9. [Monitoring](#9-monitoring)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

| Component        | Minimum Version | Notes                                    |
|------------------|-----------------|------------------------------------------|
| Python           | 3.11+           | CPython recommended                      |
| Node.js          | 20 LTS+         | Includes npm 10+                         |
| MySQL            | 8.0+            | InnoDB engine, utf8mb4 collation         |
| Redis            | 7.0+            | Used for caching and rate-limit state    |
| Docker           | 24+             | Only if using containerized deployment   |
| Docker Compose   | 2.20+           | V2 syntax (`docker compose`)             |
| Git              | 2.40+           | For cloning the repository               |

---

## 2. Local Development Setup

### 2.1 Clone the Repository

```bash
git clone <repo-url> RA-01182026
cd RA-01182026
```

### 2.2 Configure Environment Variables

```bash
# Copy the example env files
cp .env.example .env
cp .env.example backend/.env

# Edit both files. They must contain identical values.
# At minimum set: APP_ENV, DB_TYPE, DB_HOST, DB_PORT, DB_NAME, DB_USER,
#                 DB_PASSWORD, SECRET_KEY, ENCRYPTION_KEY
```

> **Important:** The backend reads its config from `backend/.env`. The root `.env` is
> used by Docker Compose. Keep them in sync.

### 2.3 MySQL Database Setup

```sql
-- Connect to MySQL as root
-- mysql -u root -p

CREATE DATABASE IF NOT EXISTS cold_email_ai_agent
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'ra_user'@'localhost'
  IDENTIFIED BY '<strong-password>';
GRANT ALL PRIVILEGES ON cold_email_ai_agent.* TO 'ra_user'@'localhost';
FLUSH PRIVILEGES;
```

### 2.4 Backend Setup (FastAPI)

```bash
cd backend

# Create and activate virtual environment
python3 -m venv venv

# Linux / macOS
source venv/bin/activate
# Windows
venv\Scriptsctivate

# Install dependencies
pip install -r requirements.txt

# Start the dev server (auto-creates tables on first run)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now available at **http://localhost:8000**.
Interactive docs at **http://localhost:8000/api/docs**.

### 2.5 Frontend Setup (Next.js 14)

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The UI is now available at **http://localhost:3000**.

### 2.6 Verify

- Backend health: `curl http://localhost:8000/health`
- Frontend: open http://localhost:3000 in a browser
- API docs: open http://localhost:8000/api/docs

---

## 3. Docker Development

The `docker-compose.yml` at the project root brings up the full stack:

```bash
# Start all services (MySQL, Redis, API, Web)
docker compose up -d

# Start backend + dependencies only
docker compose up api -d

# View logs
docker compose logs -f api
docker compose logs -f web

# Stop everything
docker compose down
```

**Default ports in Docker dev mode:**

| Service  | Host Port | Container Port |
|----------|-----------|----------------|
| MySQL    | 3307      | 3306           |
| Redis    | 6380      | 6379           |
| API      | 8000      | 8000           |
| Web      | 3003      | 3000           |

> MySQL uses port 3307 on the host to avoid conflicts with a local MySQL instance.

---

## 4. Production Deployment

### 4.1 Production Compose File (`docker-compose.prod.yml`)

```yaml
version: "3.8"

services:
  db:
    image: mysql:8.0
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: cold_email_ai_agent
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "127.0.0.1:3306:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: always
    env_file: .env
    environment:
      - APP_ENV=PROD
      - DB_TYPE=mysql
      - DB_HOST=db
      - DB_PORT=3306
      - DB_NAME=cold_email_ai_agent
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    ports:
      - "127.0.0.1:8000:8000"

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000/api/v1}
    restart: always
    ports:
      - "127.0.0.1:3000:3000"
    depends_on:
      - api

volumes:
  mysql_data:
  redis_data:
```

### 4.2 Deploy

```bash
# Build and start in production mode
docker compose -f docker-compose.prod.yml up -d --build

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### 4.3 Production Checklist

- [ ] `APP_ENV=PROD` in `.env`
- [ ] Strong, unique `SECRET_KEY` and `ENCRYPTION_KEY` (32+ random chars)
- [ ] `DB_PASSWORD` is a strong password (not the dev default)
- [ ] `CORS_ORIGINS` restricted to your domain(s)
- [ ] `EMAIL_SEND_MODE=smtp` (not mock)
- [ ] SSL/TLS termination via nginx (see section 7)
- [ ] Firewall rules: only ports 80/443 exposed publicly
- [ ] Docker containers bind to `127.0.0.1`, not `0.0.0.0`
- [ ] Automated backups configured (see section 8)
- [ ] Log rotation enabled

---

## 5. Environment Variables Reference

| Variable                      | Required | Default                           | Description                                    |
|-------------------------------|----------|-----------------------------------|------------------------------------------------|
| `APP_ENV`                     | Yes      | `DEV`                             | Environment: `TEST`, `DEV`, or `PROD`          |
| `DB_TYPE`                     | Yes      | `mysql`                           | Database engine: `mysql` or `sqlite`           |
| `DB_HOST`                     | Yes      | `localhost`                       | MySQL host                                     |
| `DB_PORT`                     | Yes      | `3306`                            | MySQL port                                     |
| `DB_NAME`                     | Yes      | `cold_email_ai_agent`            | Database name                                  |
| `DB_USER`                     | Yes      | `root`                            | Database user                                  |
| `DB_PASSWORD`                 | Yes      | �                                 | Database password                              |
| `SECRET_KEY`                  | Yes      | �                                 | JWT signing key (32+ chars)                    |
| `ENCRYPTION_KEY`              | Yes      | �                                 | Field-level encryption key                     |
| `CORS_ORIGINS`                | Yes      | `*`                               | Comma-separated allowed origins                |
| `CONTACT_PROVIDER`            | No       | `apollo`                          | Contact discovery: `apollo`, `seamless`, `mock`|
| `EMAIL_VALIDATION_PROVIDER`   | No       | `mock`                            | Email validator: `neverbounce`, `zerobounce`, etc. |
| `EMAIL_SEND_MODE`             | No       | `mock`                            | Email sending: `smtp` or `mock`                |
| `DAILY_SEND_LIMIT`            | No       | `30`                              | Max emails per mailbox per day                 |
| `COOLDOWN_DAYS`               | No       | `10`                              | Days between emails to same contact            |
| `JOB_SOURCES`                 | No       | `apollo`                          | Comma-separated job sources                    |
| `JSEARCH_API_KEY`             | No       | �                                 | JSearch API key (if using JSearch source)       |
| `GROQ_API_KEY`                | No       | �                                 | Groq AI API key for content generation         |
| `OPENAI_API_KEY`              | No       | �                                 | OpenAI API key (alternative AI provider)       |
| `NEXT_PUBLIC_API_URL`         | No       | `http://localhost:8000/api/v1`    | Frontend API base URL                          |

---

## 6. Database Migrations

The application auto-creates tables on startup via SQLAlchemy `create_all()`. For schema
changes in production, use Alembic:

### 6.1 Initialize Alembic (first time only)

```bash
cd backend
alembic init alembic

# Edit alembic.ini to set sqlalchemy.url or configure env.py to read from .env
```

### 6.2 Common Commands

```bash
# Generate a migration from model changes
alembic revision --autogenerate -m "add_new_column_to_leads"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View current migration state
alembic current

# View migration history
alembic history --verbose
```

### 6.3 Migration Best Practices

- Always review auto-generated migrations before applying
- Test migrations against a copy of production data
- Back up the database before running migrations in production
- Keep migrations small and focused on a single change

---

## 7. SSL/TLS with Nginx Reverse Proxy

### 7.1 Install Nginx and Certbot

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

### 7.2 Nginx Configuration

Create `/etc/nginx/sites-available/ra-app`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    # Frontend (Next.js)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # API (FastAPI)
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Tracking endpoints (warmup pixel and link redirect)
    location /t/ {
        proxy_pass http://127.0.0.1:8000/t/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
```

### 7.3 Enable and Obtain Certificate

```bash
sudo ln -s /etc/nginx/sites-available/ra-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Obtain SSL certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal is set up by certbot; verify with:
sudo certbot renew --dry-run
```

---

## 8. Backup Strategy

### 8.1 MySQL Backup Script

Create `/opt/ra-backups/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/ra-backups"
DB_NAME="cold_email_ai_agent"
DB_USER="root"
DB_PASS="your-db-password"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

# Create backup directory if it does not exist
mkdir -p "${BACKUP_DIR}"

# Dump and compress
mysqldump -u"${DB_USER}" -p"${DB_PASS}" \
  --single-transaction \
  --routines \
  --triggers \
  --quick \
  "${DB_NAME}" | gzip > "${BACKUP_FILE}"

echo "[$(date)] Backup created: ${BACKUP_FILE}"

# Remove backups older than retention period
find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "[$(date)] Cleanup complete. Backups older than ${RETENTION_DAYS} days removed."
```

### 8.2 Schedule via Cron

```bash
chmod +x /opt/ra-backups/backup.sh

# Run daily at 2:00 AM
crontab -e
# Add the following line:
0 2 * * * /opt/ra-backups/backup.sh >> /opt/ra-backups/backup.log 2>&1
```

### 8.3 Restore from Backup

```bash
gunzip < /opt/ra-backups/cold_email_ai_agent_20260228_020000.sql.gz | \
  mysql -u root -p cold_email_ai_agent
```

---

## 9. Monitoring

### 9.1 Health Endpoint

The backend exposes a health check at:

```
GET /health
```

Response (200 OK):

```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

Use this for load balancer health checks, uptime monitors (UptimeRobot, Pingdom), and
Docker health checks.

### 9.2 Application Logs

```bash
# Docker logs
docker compose logs -f api --tail=100
docker compose logs -f web --tail=100

# Local development: backend logs go to stdout by default.
# Set LOG_LEVEL=DEBUG in .env for verbose output.
```

### 9.3 Recommended Monitoring Stack

| Tool            | Purpose                                   |
|-----------------|-------------------------------------------|
| UptimeRobot     | External uptime monitoring (free tier)    |
| Prometheus      | Metrics collection                        |
| Grafana         | Dashboards and alerting                   |
| Loki            | Log aggregation                           |
| Sentry          | Error tracking and alerting               |

### 9.4 Key Metrics to Watch

- API response times (p50, p95, p99)
- Error rate (5xx responses)
- Database connection pool usage
- Email send success/failure rates
- Queue depth and processing latency
- Disk usage (especially backup directory)

---

## 10. Troubleshooting

### Backend will not start

**Symptom:** `ModuleNotFoundError` or import errors.

```bash
cd backend
pip install -r requirements.txt
# Ensure virtual environment is activated
```

**Symptom:** Database connection refused.

```bash
# Verify MySQL is running
mysqladmin -u root -p ping

# Check connection settings in backend/.env
# DB_HOST, DB_PORT, DB_USER, DB_PASSWORD must match your MySQL instance
```

### Frontend shows Network Error or CORS errors

1. Verify the backend is running on port 8000
2. Check `NEXT_PUBLIC_API_URL` in `frontend/.env.local` (should be `http://localhost:8000/api/v1`)
3. Check `CORS_ORIGINS` in `backend/.env` includes the frontend origin (`http://localhost:3000`)

### Docker: MySQL container keeps restarting

```bash
# Check logs
docker compose logs db

# Common fix: remove the volume and recreate
docker compose down -v
docker compose up -d
```

> **Warning:** `-v` removes all data volumes. Back up first.

### Table already exists errors on startup

This is usually harmless. SQLAlchemy `create_all()` uses `IF NOT EXISTS`. If you see
actual errors, check for schema drift between your models and the database. Run Alembic
migrations to sync.

### Emails not sending

1. Verify `EMAIL_SEND_MODE=smtp` (not `mock`)
2. Check SMTP credentials in `.env`
3. Verify sender mailbox is active and not rate-limited (`DAILY_SEND_LIMIT`)
4. Check the outreach event log for bounce/error details via the API

### JWT token errors (401 Unauthorized)

1. Ensure `SECRET_KEY` is the same across restarts (do not regenerate between deploys)
2. Tokens expire after 7 days by default; re-authenticate
3. Check that the `Authorization: Bearer <token>` header is being sent

### High memory usage

1. Check for runaway queries: `SHOW PROCESSLIST;` in MySQL
2. Restart the API container: `docker compose restart api`
3. Consider adding connection pool limits in `core/config.py`

### Port conflicts

```bash
# Find what is using a port
# Linux/macOS
lsof -i :8000
# Windows
netstat -ano | findstr :8000

# Use a different port
uvicorn app.main:app --port 8001
```

---

## Quick Command Reference

| Task                        | Command                                                        |
|-----------------------------|----------------------------------------------------------------|
| Start backend (dev)         | `cd backend && uvicorn app.main:app --reload --port 8000`      |
| Start frontend (dev)        | `cd frontend && npm run dev`                                   |
| Run all tests               | `cd backend && pytest`                                         |
| Run unit tests              | `cd backend && pytest -m unit`                                 |
| Run integration tests       | `cd backend && pytest -m integration`                          |
| Docker start (dev)          | `docker compose up -d`                                         |
| Docker start (prod)         | `docker compose -f docker-compose.prod.yml up -d --build`      |
| View API docs               | http://localhost:8000/api/docs                                 |
| Health check                | `curl http://localhost:8000/health`                            |
| Database backup             | `/opt/ra-backups/backup.sh`                                    |
| Apply migrations            | `cd backend && alembic upgrade head`                           |
