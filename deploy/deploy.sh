#!/bin/bash
# =============================================================================
# NeuraLeads AI Agent — Self-Contained Production Deployment Script
# =============================================================================
# Target: Ubuntu 24.04 VPS at 187.124.74.175
# Domain: neuraleads.ai
# App Dir: /opt/exzelon-ra-agent
# Run As: root (on VPS) or via SSH from local machine
#
# Usage (on VPS directly):
#   bash /opt/exzelon-ra-agent/deploy/deploy.sh
#
# Usage (from local machine via SSH):
#   ./deploy/vps_ssh.sh "bash /opt/exzelon-ra-agent/deploy/deploy.sh"
#
# What this script does:
#   1. Takes a pre-deploy DB backup (mysqldump | gzip) — aborts if it fails
#   2. Pulls latest code from git (master branch)
#   3. Installs backend dependencies
#   4. Builds frontend (Next.js)
#   5. Runs Alembic migrations (`alembic upgrade head`) — aborts BEFORE restart
#      if they fail, so the running services stay on the old code
#   6. Restarts services (exzelon-api, exzelon-web)
#   7. Waits up to 60s for /health, then prints /api/v1/ready
#   8. Prints the exact rollback commands (previous SHA + pre-deploy dump)
#
# Optional env overrides: DEPLOY_DB_NAME, PREDEPLOY_BACKUP_DIR, HEALTH_WAIT_SECONDS,
#   PREDEPLOY_KEEP (number of pre-deploy dumps to keep, default 10)
# =============================================================================

set -Eeuo pipefail  # -E: ERR trap (rollback hint) also fires inside functions

# ---------------------------------------------------------------------------
# Connection & Path Constants (self-contained — no external config needed)
# ---------------------------------------------------------------------------
APP_DIR="/opt/exzelon-ra-agent"
BACKEND_DIR="${APP_DIR}/backend"
FRONTEND_DIR="${APP_DIR}/frontend"
VENV_DIR="${BACKEND_DIR}/venv"
DOMAIN="neuraleads.ai"
HEALTH_URL="https://${DOMAIN}/health"
READY_URL="https://${DOMAIN}/api/v1/ready"
API_DOCS_URL="https://${DOMAIN}/api/docs"
GIT_BRANCH="master"
LINUX_USER="ra-user"

# Database + pre-deploy backup (root on the VPS dumps via the MySQL socket)
DB_NAME="${DEPLOY_DB_NAME:-exzelon_ra_agent}"
PREDEPLOY_BACKUP_DIR="${PREDEPLOY_BACKUP_DIR:-${APP_DIR}/backups}"
PREDEPLOY_KEEP="${PREDEPLOY_KEEP:-10}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-60}"

# Filled in as the deploy runs (used by the rollback instructions)
PREV_SHA=""
NEW_SHA=""
PREDEPLOY_DUMP=""
SERVICES_RESTARTED=false

# Services
API_SERVICE="exzelon-api"
WEB_SERVICE="exzelon-web"

# Frontend env (must exist for browser-side API calls)
FRONTEND_ENV_FILE="${FRONTEND_DIR}/.env.local"
FRONTEND_ENV_CONTENT="NEXT_PUBLIC_API_URL=https://${DOMAIN}/api/v1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
log_step() { echo -e "\n${BLUE}[STEP]${NC} $1"; }
log_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_fail "This script must be run as root"
        exit 1
    fi
}

print_rollback() {
    local prev="${PREV_SHA:-<previous-sha>}"
    echo ""
    echo "---------------------------- ROLLBACK ----------------------------"
    echo "Code (previous commit ${prev:0:12}):"
    echo "  cd ${APP_DIR} && git checkout ${prev}"
    echo "  cd ${BACKEND_DIR} && source venv/bin/activate && pip install -r requirements.txt"
    echo "  cd ${FRONTEND_DIR} && npm run build"
    echo "  systemctl restart ${API_SERVICE} ${WEB_SERVICE}"
    if [ -n "$PREDEPLOY_DUMP" ]; then
        echo "Database (ONLY if a migration changed/damaged data — restores the pre-deploy state,"
        echo "anything written since ${PREDEPLOY_DUMP##*/} is lost):"
        echo "  systemctl stop ${API_SERVICE}"
        echo "  gunzip -c ${PREDEPLOY_DUMP} | mysql ${DB_NAME}"
        echo "  systemctl start ${API_SERVICE}"
    fi
    echo "Then: curl -s ${HEALTH_URL} && curl -s ${READY_URL}"
    echo "------------------------------------------------------------------"
}

on_error() {
    local line="$1"
    log_fail "Deploy aborted (line ${line})."
    if [ "$SERVICES_RESTARTED" = false ]; then
        log_warn "Services were NOT restarted — production is still running the previous code."
    fi
    print_rollback
}

# ---------------------------------------------------------------------------
# Step 0: Pre-flight Checks
# ---------------------------------------------------------------------------
preflight() {
    log_step "Pre-flight checks"

    check_root

    if [ ! -d "$APP_DIR" ]; then
        log_fail "App directory not found: $APP_DIR"
        exit 1
    fi

    if [ ! -d "$VENV_DIR" ]; then
        log_fail "Python venv not found: $VENV_DIR"
        exit 1
    fi

    # Ensure frontend .env.local exists
    if [ ! -f "$FRONTEND_ENV_FILE" ]; then
        log_warn "Frontend .env.local missing — creating it"
        echo "$FRONTEND_ENV_CONTENT" > "$FRONTEND_ENV_FILE"
        chown ${LINUX_USER}:${LINUX_USER} "$FRONTEND_ENV_FILE"
        log_ok "Created $FRONTEND_ENV_FILE"
    fi

    # Check services exist (use systemctl cat which is more reliable)
    for svc in $API_SERVICE $WEB_SERVICE; do
        if ! systemctl cat "${svc}.service" &>/dev/null; then
            log_fail "Systemd service not found: ${svc}"
            log_warn "Copy service files: cp ${APP_DIR}/deploy/systemd/*.service /etc/systemd/system/ && systemctl daemon-reload"
            exit 1
        fi
    done

    log_ok "Pre-flight checks passed"
}

# ---------------------------------------------------------------------------
# Step 1a: Pre-deploy database backup (abort the deploy if it fails)
# ---------------------------------------------------------------------------
predeploy_backup() {
    log_step "Pre-deploy database backup (${DB_NAME})"
    PREV_SHA="$(cd "$APP_DIR" && git rev-parse HEAD)"
    mkdir -p "$PREDEPLOY_BACKUP_DIR"
    chmod 700 "$PREDEPLOY_BACKUP_DIR"

    local ts dump
    ts="$(date -u +%Y%m%d-%H%M%S)"
    dump="${PREDEPLOY_BACKUP_DIR}/pre-deploy-${ts}.sql.gz"

    # pipefail (set above) makes a mysqldump failure fail the whole pipeline.
    # --no-tablespaces: ra_user lacks PROCESS; harmless when run as root.
    if ! mysqldump --single-transaction --no-tablespaces --routines --triggers "$DB_NAME" \
            | gzip > "$dump"; then
        rm -f "$dump"
        log_fail "mysqldump failed — aborting deploy (nothing changed)"
        exit 1
    fi
    local trailer
    trailer=$(gunzip -c "$dump" | tail -n 3 | grep -c "Dump completed" || true)
    if ! gzip -t "$dump" || [ "${trailer:-0}" -lt 1 ]; then
        rm -f "$dump"
        log_fail "Pre-deploy dump failed its integrity check — aborting deploy (nothing changed)"
        exit 1
    fi
    chmod 600 "$dump"
    PREDEPLOY_DUMP="$dump"
    log_ok "Backup written: ${dump} ($(du -h "$dump" | cut -f1)) — previous commit ${PREV_SHA:0:7}"

    # Keep the newest $PREDEPLOY_KEEP pre-deploy dumps (pre-migrate-* dumps are left alone).
    ls -1t "${PREDEPLOY_BACKUP_DIR}"/pre-deploy-*.sql.gz 2>/dev/null \
        | tail -n +"$((PREDEPLOY_KEEP + 1))" | xargs -r rm -f -- || true
}

# ---------------------------------------------------------------------------
# Step 1: Pull Latest Code
# ---------------------------------------------------------------------------
pull_code() {
    log_step "Pulling latest code from ${GIT_BRANCH}"
    cd "$APP_DIR"

    # Stash any local changes (shouldn't exist, but safety)
    if [ -n "$(git status --porcelain)" ]; then
        log_warn "Local changes detected — stashing"
        git stash
    fi

    git fetch origin "$GIT_BRANCH"
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse "origin/${GIT_BRANCH}")

    if [ "$LOCAL" = "$REMOTE" ]; then
        log_ok "Already up to date (${LOCAL:0:7})"
        CHANGES=false
    else
        git pull origin "$GIT_BRANCH"
        NEW=$(git rev-parse HEAD)
        log_ok "Updated: ${LOCAL:0:7} → ${NEW:0:7}"
        CHANGES=true
    fi
    NEW_SHA="$(git rev-parse HEAD)"
}

# ---------------------------------------------------------------------------
# Step 2: Backend Dependencies
# ---------------------------------------------------------------------------
install_backend_deps() {
    log_step "Checking backend dependencies"
    cd "$BACKEND_DIR"
    source "${VENV_DIR}/bin/activate"

    # Always install to catch any new deps
    pip install -r requirements.txt --quiet --no-warn-script-location 2>&1 | tail -5
    log_ok "Backend dependencies up to date"
}

# ---------------------------------------------------------------------------
# Step 3: Build Frontend
# ---------------------------------------------------------------------------
build_frontend() {
    log_step "Building frontend (Next.js)"
    cd "$FRONTEND_DIR"

    # Verify .env.local
    if ! grep -q "NEXT_PUBLIC_API_URL" "$FRONTEND_ENV_FILE" 2>/dev/null; then
        log_fail "NEXT_PUBLIC_API_URL not set in $FRONTEND_ENV_FILE"
        exit 1
    fi

    # Install npm deps if node_modules missing or package-lock changed
    if [ ! -d "node_modules" ] || [ "package-lock.json" -nt "node_modules/.package-lock.json" ]; then
        log_step "Installing npm dependencies"
        npm ci --silent 2>&1 | tail -3
    fi

    npm run build 2>&1 | tail -10
    log_ok "Frontend build complete"
}

# ---------------------------------------------------------------------------
# Step 3b: Database migrations (Alembic) — right before the restart, because the
# old code still serving traffic cannot read a migrated schema for long.
# ---------------------------------------------------------------------------
run_migrations() {
    log_step "Running database migrations (alembic upgrade head)"
    cd "$BACKEND_DIR"
    local before after
    before="$("${VENV_DIR}/bin/alembic" current 2>/dev/null | tail -n 1 || true)"
    echo "  alembic current (before): ${before:-<none>}"

    if ! "${VENV_DIR}/bin/alembic" upgrade head; then
        log_fail "alembic upgrade head FAILED — services NOT restarted (still on old code)."
        echo "  Inspect:  cd ${BACKEND_DIR} && venv/bin/alembic current && venv/bin/alembic history | head"
        if [ -n "$PREDEPLOY_DUMP" ]; then
            echo "  If the migration left the schema half-applied, restore the pre-deploy dump:"
            echo "    gunzip -c ${PREDEPLOY_DUMP} | mysql ${DB_NAME}"
        fi
        exit 1
    fi

    after="$("${VENV_DIR}/bin/alembic" current 2>/dev/null | tail -n 1 || true)"
    log_ok "alembic current: ${after:-<unknown>}"
}

# ---------------------------------------------------------------------------
# Step 4: Restart Services
# ---------------------------------------------------------------------------
restart_services() {
    log_step "Restarting services"

    SERVICES_RESTARTED=true
    systemctl restart "$API_SERVICE"
    log_ok "Restarted $API_SERVICE"

    systemctl restart "$WEB_SERVICE"
    log_ok "Restarted $WEB_SERVICE"
}

# ---------------------------------------------------------------------------
# Step 5: Health Checks
# ---------------------------------------------------------------------------
health_checks() {
    log_step "Running health checks"

    # Check systemd service status
    for svc in $API_SERVICE $WEB_SERVICE; do
        if systemctl is-active --quiet "$svc"; then
            log_ok "$svc is running"
        else
            log_fail "$svc is NOT running"
            systemctl status "$svc" --no-pager -l | tail -20
            return 1
        fi
    done

    # HTTP health check — 4 uvicorn workers run the startup lifespan (seeds,
    # legacy migrations) before accepting traffic, so nginx returns 502 for a
    # while after every restart. Poll for up to $HEALTH_WAIT_SECONDS.
    local waited=0 HTTP_CODE="000"
    while [ "$waited" -lt "$HEALTH_WAIT_SECONDS" ]; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH_URL" 2>/dev/null || true)
        [ -n "$HTTP_CODE" ] || HTTP_CODE="000"
        if [ "$HTTP_CODE" = "200" ]; then
            break
        fi
        sleep 2
        waited=$((waited + 2))
    done
    if [ "$HTTP_CODE" = "200" ]; then
        log_ok "Health endpoint returned 200 after ~${waited}s"
    else
        log_fail "Health check did not return 200 within ${HEALTH_WAIT_SECONDS}s (last: $HTTP_CODE)"
        journalctl -u "$API_SERVICE" --since "-2min" --no-pager | tail -30 || true
        return 1
    fi

    # Readiness (DB, Redis, scheduler heartbeat, disk, backup age). Printed for
    # the operator; a 503 here is a warning, not a failed deploy (e.g. a brand-new
    # box has no daily backup yet). The watchdog alerts if it stays failing.
    local ready_file ready_code
    ready_file="$(mktemp)"
    ready_code=$(curl -s -o "$ready_file" -w "%{http_code}" --max-time 15 "$READY_URL" 2>/dev/null || true)
    echo "  ${READY_URL} -> ${ready_code:-000}"
    if command -v python3 &>/dev/null; then
        python3 -m json.tool < "$ready_file" 2>/dev/null || cat "$ready_file"
    else
        cat "$ready_file"
    fi
    echo ""
    rm -f "$ready_file"
    if [ "$ready_code" = "200" ]; then
        log_ok "Readiness: ready"
    else
        log_warn "Readiness returned ${ready_code:-000} — check the 'failed' list above"
    fi

    # Check nginx
    if systemctl is-active --quiet nginx; then
        log_ok "nginx is running"
    else
        log_fail "nginx is NOT running"
        return 1
    fi

    # Check MySQL
    if systemctl is-active --quiet mysql; then
        log_ok "MySQL is running"
    else
        log_fail "MySQL is NOT running"
        return 1
    fi

    log_ok "All health checks passed"
}

# ---------------------------------------------------------------------------
# Step 6: Summary
# ---------------------------------------------------------------------------
summary() {
    log_step "Deployment Summary"
    echo "----------------------------------------------"
    echo "  Domain:    https://${DOMAIN}"
    echo "  Health:    ${HEALTH_URL}"
    echo "  API Docs:  ${API_DOCS_URL}"
    echo "  Commit:    $(cd $APP_DIR && git rev-parse --short HEAD) (previous: ${PREV_SHA:0:7})"
    echo "  DB backup: ${PREDEPLOY_DUMP:-<none>}"
    echo "  Branch:    ${GIT_BRANCH}"
    echo "  Time:      $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "----------------------------------------------"

    # Show service resource usage
    echo ""
    echo "Service Status:"
    for svc in $API_SERVICE $WEB_SERVICE nginx mysql redis-server; do
        STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
        if [ "$STATUS" = "active" ]; then
            echo -e "  ${GREEN}●${NC} $svc"
        else
            echo -e "  ${RED}●${NC} $svc ($STATUS)"
        fi
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo "=============================================="
    echo " NeuraLeads AI Agent — Production Deploy"
    echo " $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "=============================================="

    trap 'on_error $LINENO' ERR

    preflight
    predeploy_backup
    pull_code
    install_backend_deps
    build_frontend
    run_migrations
    restart_services
    health_checks
    summary

    trap - ERR
    print_rollback
    echo ""
    log_ok "Deployment complete!"
}

main "$@"
