# Disaster Recovery Runbook — Exzelon RA Agent (NeuraLeads)

> Owner: platform team · Last updated: 2026-10-12 (Plan_Launch_Readiness_6 B1-B4, M3-M5; was ELR-018)
> Scope: recover the production service (`neuraleads.ai`, VPS `187.124.74.175`)
> after data loss, VPS failure, or a bad deploy.

## Recovery objectives
- **RPO (max data loss): 24h** — `job_daily_backup` runs daily at **02:00 UTC**; every deploy
  also takes a pre-deploy dump. Tighten by increasing backup frequency if needed.
- **RTO (max downtime): 2h** — provision host + restore latest backup + restart services.
  The restore drill (below) prints the measured restore time; record it in the drill log.

## Backup inventory
| Kind | Where | Retention | Made by |
|---|---|---|---|
| Daily | `backend/data/backups/exzelon_ra_agent_<YYYYMMDD>_<HHMMSS>.sql.gz` | **max(`backup_retention_days` setting, `BACKUP_LOCAL_RETENTION_DAYS`=14)** days | `job_daily_backup` (02:00 UTC), cleanup `job_backup_cleanup` (02:30 UTC) |
| Pre-deploy | `/opt/exzelon-ra-agent/backups/pre-deploy-<ts>.sql.gz` | newest 10 | `deploy/deploy.sh` (aborts the deploy if the dump fails) |
| Off-site | `s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/<file>.sql.gz[.enc]` | 30 days (pruned after each upload) | `create_backup()` when `BACKUP_S3_BUCKET` is set |

- `BACKUP_LOCAL_RETENTION_DAYS` is a **floor**: the admin setting `backup_retention_days`
  (Settings UI, 1-90, default 3) can only lengthen retention, never shorten it below 14.
- Every daily dump is **integrity-checked** right after it is written (`verify_backup()`):
  full gzip stream read (= `gzip -t`), size ≥ 1 MB, contains `CREATE TABLE`, ends with
  mysqldump's `-- Dump completed` trailer. A dump that fails is renamed `*.sql.gz.failed`
  (so it is never counted or restored), and an alert email goes out.
- Off-site copies are Fernet-encrypted (`.enc`) when `BACKUP_ENCRYPT=true` (default) with
  `ENCRYPTION_KEY`; the SHA-256 of the unencrypted `.sql.gz` is stored in object metadata `sha256`.
- `mysqldump` runs with `--no-tablespaces` (ra_user has no PROCESS privilege).

## Monitoring & alerts
All alerts are emailed to **`ALERT_EMAIL`** (default `info@neuraleads.ai`) through the global
system mailer (Resend — `RESEND_API_KEY` + `RESEND_FROM_EMAIL` must be set). Each alert kind
is sent at most once per `ALERT_MIN_INTERVAL_MINUTES` (15).

| Alert kind | Trigger |
|---|---|
| `backup_failed` | daily backup failed (mysqldump error/timeout) or failed its integrity check |
| `backup_offsite_failed` | off-site upload failed (local backup still intact) |
| `unhandled_exception` | any 500 from an unhandled exception (subject has method + path; body has traceback, never the request body) |
| watchdog DOWN / RECOVERED | `/api/v1/ready` failed 2 consecutive 5-min checks / is healthy again (one email each) |

**Readiness probe** — `GET https://neuraleads.ai/api/v1/ready` (also `/ready` on the API port).
Returns 200 or 503 with per-check JSON: `database` (critical), `scheduler` heartbeat ≤ 10 min
(critical), `backup` newest local dump ≤ 26h (critical), `disk` free % on the data dir
(warn < 10 %, critical < 5 %), `redis` (never critical). `/health` is unchanged (DB only).

**Watchdog** — `deploy/watchdog/neuraleads-watchdog.{sh,service,timer}`, runs every 5 min on the
VPS. State in `/var/lib/neuraleads-watchdog/`. Install:
```bash
cp /opt/exzelon-ra-agent/deploy/watchdog/neuraleads-watchdog.service \
   /opt/exzelon-ra-agent/deploy/watchdog/neuraleads-watchdog.timer /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now neuraleads-watchdog.timer
systemctl list-timers neuraleads-watchdog.timer          # next run
systemctl start neuraleads-watchdog.service && journalctl -u neuraleads-watchdog -n 20
# Test the mail path (sends one real email to ALERT_EMAIL):
cd /opt/exzelon-ra-agent/backend && runuser -u ra-user -- venv/bin/python -m app.services.alerting \
    send --kind test --no-dedup --subject "Alert path test" --body "watchdog mail test"
```
Optional overrides in `/etc/default/neuraleads-watchdog` (`READY_URL`, `FAIL_THRESHOLD`, ...).
The watchdog runs ON the VPS, so it cannot report a dead VPS/network — pair it with an
external uptime monitor on `/health` for that case.

## Off-site setup — Backblaze B2 (user action, one time)
1. **Create a private bucket** — B2 console → Buckets → Create a Bucket: name e.g.
   `neuraleads-db-backups`, **Files in Bucket: Private**, default encryption on (SSE-B2) is fine.
   Note the bucket's **Endpoint** (e.g. `s3.us-west-004.backblazeb2.com`).
2. **Lifecycle** — Bucket Settings → Lifecycle: *Keep only the last version of the file*
   (so the app's 30-day prune actually frees space instead of leaving hidden versions).
3. **Create an application key** — App Keys → Add a New Application Key: name
   `neuraleads-backups`, **Allow access to bucket: only `neuraleads-db-backups`**, type
   **Read and Write**, leave "file name prefix" empty. Copy the **keyID** and
   **applicationKey** (shown once).
4. **Set the env keys** in `/opt/exzelon-ra-agent/backend/.env` (APP_ENV=PROD → `PROD_` prefix;
   env_loader strips it):
   ```
   PROD_BACKUP_S3_BUCKET=neuraleads-db-backups
   PROD_BACKUP_S3_PREFIX=db-backups
   PROD_BACKUP_S3_ENDPOINT_URL=https://s3.us-west-004.backblazeb2.com   # your bucket's endpoint
   PROD_AWS_ACCESS_KEY_ID=<B2 keyID>
   PROD_AWS_SECRET_ACCESS_KEY=<B2 applicationKey>
   PROD_BACKUP_ENCRYPT=true            # needs PROD_ENCRYPTION_KEY (already set on prod)
   # PROD_AWS_DEFAULT_REGION=us-west-004  # optional — derived from the endpoint host
   ```
   The region is derived from the B2 endpoint host, and boto3's newer default CRC32 checksum
   headers are disabled on custom endpoints (B2 rejects some of them).
   **Keep a copy of `ENCRYPTION_KEY` outside the VPS** (password manager) — without it the
   off-site `.enc` files cannot be decrypted.
5. `systemctl restart exzelon-api`
6. **Verify** — trigger a backup (Admin → Backups → Create, or wait for 02:00 UTC), then:
   ```bash
   journalctl -u exzelon-api --since "10 min ago" | grep -E "backup_offsite_(uploaded|failed)"
   ```
   and check the object appears in the B2 bucket browser under `db-backups/`. A failure also
   sends a `backup_offsite_failed` alert email.

## Restore procedure
1. **Provision** a host with MySQL 8, Python 3.12+, and the app at `/opt/exzelon-ra-agent/`
   (see `CLAUDE_REFERENCE/deployment.md`). Restore the `.env` from your secret store.
2. **Fetch the latest backup**:
   - Local present? use `backend/data/backups/…` (or `backups/pre-deploy-…` for a deploy rollback).
   - Else from B2 (any S3 client, e.g. `aws` CLI with the B2 key):
     `aws s3 cp --endpoint-url $BACKUP_S3_ENDPOINT_URL s3://$BACKUP_S3_BUCKET/db-backups/<file>.enc .`
3. **Decrypt** (if `.enc`): Fernet-decrypt with `ENCRYPTION_KEY` →
   `python -c "import os;from cryptography.fernet import Fernet; open('b.sql.gz','wb').write(Fernet(os.environ['ENCRYPTION_KEY'].encode()).decrypt(open('<file>.enc','rb').read()))"`
4. **Verify integrity**: `sha256sum b.sql.gz` must equal the object metadata `sha256`; `gzip -t b.sql.gz`.
5. **Restore**: prefer the admin API/`restore_backup()` (it snapshots first). Manual fallback:
   `gunzip -c b.sql.gz | mysql exzelon_ra_agent` (as root on the VPS). Dumps contain no
   `USE`/`CREATE DATABASE`, so the target schema is whatever you name on the command line.
6. **Migrations**: `cd backend && venv/bin/alembic upgrade head && venv/bin/alembic current`.
7. **Restart + check**: `systemctl restart exzelon-api exzelon-web`, then
   `curl -fsS https://neuraleads.ai/health` and `curl -s https://neuraleads.ai/api/v1/ready`.
8. **Post-restore**: verify a tenant login + a dashboard load; re-point DNS if the host changed.

## Bad-deploy rollback
`deploy/deploy.sh` prints the exact commands at the end of every run (and on failure):
```bash
cd /opt/exzelon-ra-agent && git checkout <previous-sha>
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm run build
systemctl restart exzelon-api exzelon-web
# Only if a migration damaged data (loses writes made since the dump):
systemctl stop exzelon-api && gunzip -c /opt/exzelon-ra-agent/backups/pre-deploy-<ts>.sql.gz | mysql exzelon_ra_agent && systemctl start exzelon-api
```
If `alembic upgrade head` fails during a deploy, the script stops **before** restarting, so
production keeps running the previous code; fix forward or roll the checkout back.

## Restore drill (B4)
`deploy/restore_drill.sh` restores the newest local dump into the scratch database
**`exzelon_restore_drill`** (fixed name; refuses a dump containing `USE`/`CREATE DATABASE`),
compares row counts of `tenants, users, lead_details, contact_details, sender_mailboxes,
credit_usage` with production, prints PASS/FAIL + restore time, and **always drops the scratch
database** (EXIT trap). It never writes to `exzelon_ra_agent`.
```bash
bash /opt/exzelon-ra-agent/deploy/restore_drill.sh                    # newest dump
bash /opt/exzelon-ra-agent/deploy/restore_drill.sh /path/to/dump.sql.gz
```
A table passes when `|prod − restored| ≤ max(50, 20 % of prod)` (the dump is up to 24h old;
tune with `DRILL_TOLERANCE_ABS` / `DRILL_TOLERANCE_PCT`). Exit 0 = PASS, 1 = FAIL, 2 = could not run.
Needs free disk ≈ the DB size while it runs.

**Cadence:** run it after enabling this runbook, then **monthly**, and once quarterly from an
off-site copy (download + decrypt, then pass the file path). Record results below.

### Drill log
| Date (UTC) | Dump | Restore time | Result | Notes |
|---|---|---|---|---|
| _pending first run_ | | | | |
