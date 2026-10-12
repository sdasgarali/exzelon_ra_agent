#!/bin/bash
# =============================================================================
# NeuraLeads readiness watchdog (Plan_Launch_Readiness_6 M3)
# =============================================================================
# Run every 5 min by neuraleads-watchdog.timer. Curls the API readiness probe;
# after FAIL_THRESHOLD consecutive failures it emails ONE alert, and ONE recovery
# email when the probe is healthy again. State lives in $STATE_DIR so alerts are
# not repeated every 5 minutes while the site stays down.
#
# Mail goes through the backend's alert CLI (python -m app.services.alerting),
# which uses the global system mailer (Resend) and needs neither the API nor
# MySQL to be up. Recipient = ALERT_EMAIL in backend/.env.
#
# Overrides (optional): /etc/default/neuraleads-watchdog
#   READY_URL, FAIL_THRESHOLD, STATE_DIR, BACKEND_DIR, RUN_AS, CURL_TIMEOUT
# =============================================================================
set -uo pipefail

READY_URL="${READY_URL:-https://neuraleads.ai/api/v1/ready}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"
STATE_DIR="${STATE_DIR:-/var/lib/neuraleads-watchdog}"
BACKEND_DIR="${BACKEND_DIR:-/opt/exzelon-ra-agent/backend}"
RUN_AS="${RUN_AS:-ra-user}"
CURL_TIMEOUT="${CURL_TIMEOUT:-20}"

FAILS_FILE="${STATE_DIR}/consecutive_failures"
ALERTED_FILE="${STATE_DIR}/alert_open"
LAST_FILE="${STATE_DIR}/last_result"

log() { echo "[neuraleads-watchdog] $*"; }

mkdir -p "$STATE_DIR"

read_int() {
    local v
    v="$(cat "$1" 2>/dev/null || echo 0)"
    [[ "$v" =~ ^[0-9]+$ ]] || v=0
    echo "$v"
}

send_mail() {
    # $1 = subject, stdin = body. Returns the CLI's exit code (0 = sent).
    local subject="$1"
    local py="${BACKEND_DIR}/venv/bin/python"
    if [ ! -x "$py" ]; then
        log "ERROR: $py not found — cannot send alert '$subject'"
        return 1
    fi
    if id "$RUN_AS" &>/dev/null && [ "$(id -u)" -eq 0 ]; then
        (cd "$BACKEND_DIR" && runuser -u "$RUN_AS" -- "$py" -m app.services.alerting send \
            --kind watchdog --no-dedup --subject "$subject" --body -)
    else
        (cd "$BACKEND_DIR" && "$py" -m app.services.alerting send \
            --kind watchdog --no-dedup --subject "$subject" --body -)
    fi
}

BODY_FILE="$(mktemp)"
trap 'rm -f "$BODY_FILE"' EXIT

HTTP_CODE="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' --max-time "$CURL_TIMEOUT" "$READY_URL" 2>>"$BODY_FILE" || true)"
[ -n "$HTTP_CODE" ] || HTTP_CODE="000"
NOW="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
FAILS="$(read_int "$FAILS_FILE")"
ALERTED="$(read_int "$ALERTED_FILE")"

if [ "$HTTP_CODE" = "200" ]; then
    echo "ok $HTTP_CODE $NOW" > "$LAST_FILE"
    echo 0 > "$FAILS_FILE"
    if [ "$ALERTED" -eq 1 ]; then
        log "recovered ($READY_URL -> 200) — sending recovery email"
        if printf 'NeuraLeads is healthy again.\n\nURL: %s\nRecovered at: %s\nConsecutive failures before recovery: %s\n\n%s\n' \
                "$READY_URL" "$NOW" "$FAILS" "$(head -c 3000 "$BODY_FILE")" \
                | send_mail "RECOVERED: neuraleads.ai is ready again"; then
            echo 0 > "$ALERTED_FILE"
        else
            log "recovery email failed — will retry on the next run"
        fi
    else
        log "ok ($HTTP_CODE)"
    fi
    exit 0
fi

FAILS=$((FAILS + 1))
echo "$FAILS" > "$FAILS_FILE"
echo "fail $HTTP_CODE $NOW" > "$LAST_FILE"
log "FAIL #$FAILS ($READY_URL -> $HTTP_CODE)"

if [ "$FAILS" -ge "$FAIL_THRESHOLD" ] && [ "$ALERTED" -eq 0 ]; then
    log "threshold reached — sending alert email"
    if printf 'The NeuraLeads readiness probe has failed %s consecutive checks (every 5 min).\n\nURL: %s\nHTTP status: %s\nTime: %s\n\nResponse / error (first 3000 bytes):\n%s\n\nFirst steps on the VPS:\n  systemctl status exzelon-api exzelon-web nginx mysql\n  journalctl -u exzelon-api --since "30 min ago"\n  curl -s http://127.0.0.1:8000/ready\n\nYou will get ONE recovery email when it is healthy again.\n' \
            "$FAILS" "$READY_URL" "$HTTP_CODE" "$NOW" "$(head -c 3000 "$BODY_FILE")" \
            | send_mail "DOWN: neuraleads.ai readiness failing (HTTP $HTTP_CODE)"; then
        echo 1 > "$ALERTED_FILE"
    else
        log "alert email failed — will retry on the next run"
    fi
fi
exit 0
