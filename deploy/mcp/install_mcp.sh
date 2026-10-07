#!/usr/bin/env bash
# Install or update the NeuraLeads MCP connector on the VPS. Idempotent; run as root:
#   bash /opt/exzelon-ra-agent/deploy/mcp/install_mcp.sh
# Before the FIRST run: confirm the port is free (`ss -tlnp | grep :8010`), and if it is not,
# set MCP_HTTP_PORT in mcp_server/.env and the nginx upstream to a free one.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/exzelon-ra-agent}"
MCP_DIR="${APP_DIR}/mcp_server"
VENV="${MCP_DIR}/.venv"
ENV_FILE="${MCP_DIR}/.env"
SERVICE="neuraleads-mcp"
PY="${PYTHON:-python3}"

log() { printf '[mcp-install] %s\n' "$*"; }
fail() { printf '[mcp-install] ERROR: %s\n' "$*" >&2; exit 1; }

[ -d "$MCP_DIR" ] || fail "missing $MCP_DIR (deploy the code first)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail "Python 3.11+ required"

if [ ! -x "${VENV}/bin/python" ]; then
    log "creating venv"
    "$PY" -m venv "$VENV"
fi
log "installing package"
"${VENV}/bin/pip" install --quiet --upgrade pip
"${VENV}/bin/pip" install --quiet "$MCP_DIR"

if [ ! -f "$ENV_FILE" ]; then
    log "writing default $ENV_FILE"
    cat > "$ENV_FILE" <<ENV
NEURALEADS_API_URL=http://127.0.0.1:8000/api/v1
MCP_HTTP_HOST=127.0.0.1
MCP_HTTP_PORT=8010
MCP_ALLOWED_HOSTS=neuraleads.ai,www.neuraleads.ai,127.0.0.1:*,localhost:*
MCP_LOG_LEVEL=INFO
NEURALEADS_MCP_READ_ONLY=false
ENV
    chmod 640 "$ENV_FILE"
fi
chown -R ra-user:ra-user "$MCP_DIR"

log "installing systemd unit"
cp "${APP_DIR}/deploy/systemd/${SERVICE}.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --quiet "$SERVICE"
systemctl restart "$SERVICE"

PORT=$(grep -E '^MCP_HTTP_PORT=' "$ENV_FILE" | cut -d= -f2)
PORT="${PORT:-8010}"
for _ in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
        log "healthy on 127.0.0.1:${PORT}"
        curl -fsS "http://127.0.0.1:${PORT}/healthz"; echo
        exit 0
    fi
    sleep 1
done
systemctl status "$SERVICE" --no-pager -l | tail -20
fail "health check failed"
