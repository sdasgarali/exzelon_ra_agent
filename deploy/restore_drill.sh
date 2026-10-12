#!/bin/bash
# =============================================================================
# NeuraLeads restore drill (Plan_Launch_Readiness_6 B4)
# =============================================================================
# Restores the newest local DB dump into a SCRATCH database, compares row counts
# of key tables against production, prints a PASS/FAIL report, and ALWAYS drops
# the scratch database (trap on EXIT). It never writes to the production schema:
# the scratch name is fixed, checked against the prod name, and the dump is
# refused if it contains a USE / CREATE DATABASE statement that could redirect
# the restore.
#
# Usage (on the VPS, as root — uses the MySQL socket):
#   bash /opt/exzelon-ra-agent/deploy/restore_drill.sh               # newest dump
#   bash /opt/exzelon-ra-agent/deploy/restore_drill.sh /path/x.sql.gz  # specific dump
#
# Env overrides: PROD_DB (default exzelon_ra_agent), MYSQL_CMD (default "mysql"),
#   DRILL_TOLERANCE_PCT (default 20), DRILL_TOLERANCE_ABS (default 50)
# Row counts are expected to drift a little (the dump is up to 24h old), so a
# table passes when |prod - restored| <= max(ABS, prod * PCT / 100).
# Exit code: 0 = PASS, 1 = FAIL, 2 = could not run.
# =============================================================================
set -uo pipefail

APP_DIR="/opt/exzelon-ra-agent"
PROD_DB="${PROD_DB:-exzelon_ra_agent}"
readonly SCRATCH_DB="exzelon_restore_drill"     # fixed on purpose — not overridable
MYSQL_CMD="${MYSQL_CMD:-mysql}"
TOL_PCT="${DRILL_TOLERANCE_PCT:-20}"
TOL_ABS="${DRILL_TOLERANCE_ABS:-50}"
KEY_TABLES=(tenants users lead_details contact_details sender_mailboxes credit_usage)

die() { echo "[restore-drill] ERROR: $*" >&2; exit 2; }
q()   { $MYSQL_CMD -N -B -e "$1" 2>/dev/null; }

# --- Safety guards ------------------------------------------------------------
[ "$SCRATCH_DB" != "$PROD_DB" ] || die "scratch DB name equals PROD_DB — refusing"
[[ "$SCRATCH_DB" == exzelon_restore_drill ]] || die "unexpected scratch DB name"
command -v "${MYSQL_CMD%% *}" >/dev/null || die "mysql client not found"
q "SELECT 1" >/dev/null || die "cannot connect to MySQL with '$MYSQL_CMD' (run as root on the VPS)"
[ -n "$(q "SHOW DATABASES LIKE '${PROD_DB}'")" ] || die "production DB '${PROD_DB}' not found"

# --- Pick the dump --------------------------------------------------------------
DUMP="${1:-}"
if [ -z "$DUMP" ]; then
    DUMP="$(ls -1t "${APP_DIR}"/backend/data/backups/exzelon_ra_agent_*.sql.gz \
                    "${APP_DIR}"/backups/pre-deploy-*.sql.gz 2>/dev/null | head -n 1 || true)"
fi
[ -n "$DUMP" ] && [ -f "$DUMP" ] || die "no dump found (looked in backend/data/backups and backups/)"
echo "[restore-drill] dump: $DUMP ($(du -h "$DUMP" | cut -f1), modified $(date -u -r "$DUMP" '+%Y-%m-%d %H:%M UTC'))"

gzip -t "$DUMP" || die "gzip integrity check failed for $DUMP"
# grep -c (not -q/-m1): reads the whole stream, so no SIGPIPE false-negative under pipefail.
redirects=$(gunzip -c "$DUMP" | grep -ciE '^[[:space:]]*(USE[[:space:]]|CREATE[[:space:]]+DATABASE)' || true)
if [ "${redirects:-0}" -gt 0 ]; then
    die "dump contains USE/CREATE DATABASE — it could restore into another schema; refusing"
fi

# --- Always clean up ------------------------------------------------------------
cleanup() {
    $MYSQL_CMD -e "DROP DATABASE IF EXISTS \`${SCRATCH_DB}\`" 2>/dev/null \
        && echo "[restore-drill] scratch database ${SCRATCH_DB} dropped" \
        || echo "[restore-drill] WARNING: could not drop ${SCRATCH_DB} — drop it by hand" >&2
}
trap cleanup EXIT

$MYSQL_CMD -e "DROP DATABASE IF EXISTS \`${SCRATCH_DB}\`; CREATE DATABASE \`${SCRATCH_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" \
    || die "could not create ${SCRATCH_DB}"

echo "[restore-drill] restoring into ${SCRATCH_DB} ..."
START=$(date +%s)
if ! gunzip -c "$DUMP" | $MYSQL_CMD "$SCRATCH_DB"; then
    echo "[restore-drill] RESULT: FAIL — mysql restore returned an error"
    exit 1
fi
ELAPSED=$(( $(date +%s) - START ))

# --- Compare ------------------------------------------------------------------------
RESULT=PASS
prod_tables=$(q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${PROD_DB}'")
drill_tables=$(q "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${SCRATCH_DB}'")

echo ""
echo "================ RESTORE DRILL REPORT ================"
echo "Dump:          $DUMP"
echo "Restore time:  ${ELAPSED}s"
echo "Tables:        prod=${prod_tables:-?}  restored=${drill_tables:-?}"
printf "%-20s %12s %12s %8s  %s\n" "table" "prod" "restored" "diff" "status"
for t in "${KEY_TABLES[@]}"; do
    p=$(q "SELECT COUNT(*) FROM \`${PROD_DB}\`.\`${t}\`")
    r=$(q "SELECT COUNT(*) FROM \`${SCRATCH_DB}\`.\`${t}\`")
    if [ -z "$p" ]; then
        printf "%-20s %12s %12s %8s  %s\n" "$t" "-" "${r:--}" "-" "SKIP (not in prod)"
        continue
    fi
    if [ -z "$r" ]; then
        printf "%-20s %12s %12s %8s  %s\n" "$t" "$p" "MISSING" "-" "FAIL"
        RESULT=FAIL
        continue
    fi
    diff=$(( p > r ? p - r : r - p ))
    allowed=$(( p * TOL_PCT / 100 ))
    [ "$allowed" -ge "$TOL_ABS" ] || allowed=$TOL_ABS
    status=OK
    if [ "$diff" -gt "$allowed" ] || { [ "$p" -gt 0 ] && [ "$r" -eq 0 ]; }; then
        status=FAIL
        RESULT=FAIL
    fi
    printf "%-20s %12s %12s %8s  %s\n" "$t" "$p" "$r" "$diff" "$status"
done
if [ -n "$prod_tables" ] && [ -n "$drill_tables" ] && [ "$drill_tables" -lt "$prod_tables" ]; then
    echo "NOTE: fewer tables restored than in prod (tables created after the dump?)"
fi
echo "RESULT: ${RESULT}"
echo "======================================================"
[ "$RESULT" = PASS ] && exit 0 || exit 1
