#!/bin/bash
# =============================================================================
# NeuraLeads AI Agent — Self-Contained Production Deployment Script
# =============================================================================
# Target: Ubuntu 24.04 VPS at 187.124.74.175
# Domain: ra.partnerwithus.tech
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
#   1. Pulls latest code from git (master branch)
#   2. Installs backend dependencies (if requirements.txt changed)
#   3. Runs database migrations (auto-applied on app startup)
#   4. Builds frontend (Next.js)
#   5. Restarts services (exzelon-api, exzelon-web)
#   6. Runs health checks
#   7. Shows service status
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Connection & Path Constants (self-contained — no external config needed)
# ---------------------------------------------------------------------------
APP_DIR="/opt/exzelon-ra-agent"
BACKEND_DIR="${APP_DIR}/backend"
FRONTEND_DIR="${APP_DIR}/frontend"
VENV_DIR="${BACKEND_DIR}/venv"
DOMAIN="ra.partnerwithus.tech"
HEALTH_URL="https://${DOMAIN}/health"
API_DOCS_URL="https://${DOMAIN}/api/docs"
GIT_BRANCH="master"
LINUX_USER="ra-user"

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

    # Check services exist
    for svc in $API_SERVICE $WEB_SERVICE; do
        if ! systemctl list-unit-files | grep -q "^${svc}.service"; then
            log_fail "Systemd service not found: ${svc}"
            log_warn "Copy service files: cp ${APP_DIR}/deploy/systemd/*.service /etc/systemd/system/ && systemctl daemon-reload"
            exit 1
        fi
    done

    log_ok "Pre-flight checks passed"
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
# Step 4: Restart Services
# ---------------------------------------------------------------------------
restart_services() {
    log_step "Restarting services"

    systemctl restart "$API_SERVICE"
    log_ok "Restarted $API_SERVICE"

    systemctl restart "$WEB_SERVICE"
    log_ok "Restarted $WEB_SERVICE"

    # Give services time to start
    sleep 3
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

    # HTTP health check (retry up to 5 times)
    for i in 1 2 3 4 5; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ]; then
            log_ok "Health endpoint returned 200"
            break
        else
            if [ "$i" -lt 5 ]; then
                log_warn "Health check attempt $i returned $HTTP_CODE — retrying in 3s..."
                sleep 3
            else
                log_fail "Health check failed after 5 attempts (last: $HTTP_CODE)"
                return 1
            fi
        fi
    done

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
    echo "  Commit:    $(cd $APP_DIR && git rev-parse --short HEAD)"
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

    preflight
    pull_code
    install_backend_deps
    build_frontend
    restart_services
    health_checks
    summary

    echo ""
    log_ok "Deployment complete!"
}

main "$@"
