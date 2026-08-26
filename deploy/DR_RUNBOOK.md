# Disaster Recovery Runbook — Exzelon RA Agent (NeuraLeads)

> Owner: platform team · Last updated: 2026-08-25 (ELR-018)
> Scope: recover the production service (`ra.partnerwithus.tech`, VPS `187.124.74.175`)
> after data loss, VPS failure, or a bad deploy.

## Recovery objectives
- **RPO (max data loss): 24h** — backups run daily (`job_daily_backup`, 03:00). Tighten by
  increasing backup frequency if the business needs a smaller window.
- **RTO (max downtime): 2h** — provision host + restore latest backup + restart services.

## Backup inventory
- **Local**: `backend/data/backups/exzelon_ra_agent_<YYYYMMDD>_<HHMMSS>.sql.gz` (mysqldump + gzip),
  retained per `BACKUP_RETENTION_DAYS`. Each carries a SHA-256 (logged as `sha256=` on `Backup created`).
- **Offsite** (ELR-018): uploaded to `s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/…` when
  `BACKUP_S3_BUCKET` is set. Fernet-encrypted (`.enc`) when `BACKUP_ENCRYPT=true` (default),
  key = `ENCRYPTION_KEY`. Checksum stored in object metadata.
- **Monitoring**: alert on the structured log event **`backup_offsite_failed`** (offsite upload
  failed) and on the absence of a daily `backup_offsite_uploaded` event.

## Config (set on the host `.env`, secrets never in git)
```
BACKUP_S3_BUCKET=<bucket>
BACKUP_S3_PREFIX=db-backups
BACKUP_S3_ENDPOINT_URL=            # only for S3-compatible providers (e.g. Backblaze/Wasabi)
BACKUP_ENCRYPT=true                # Fernet-encrypt with ENCRYPTION_KEY
# AWS creds via standard env: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION
SENTRY_DSN=<dsn>                   # error tracking (ELR-017), inert if unset
```

## Restore procedure
1. **Provision** a host with MySQL 8, Python 3.12+, and the app at `/opt/exzelon-ra-agent/`
   (see `CLAUDE_REFERENCE/deployment.md`). Restore the `.env` from your secret store.
2. **Fetch the latest backup**:
   - Local present? use `backend/data/backups/…`.
   - Else from offsite: `aws s3 cp s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/<file>[.enc] .`
3. **Decrypt** (if `.enc`): Fernet-decrypt with `ENCRYPTION_KEY` →
   `python -c "from cryptography.fernet import Fernet,os; open('b.sql.gz','wb').write(Fernet(os.environ['ENCRYPTION_KEY'].encode()).decrypt(open('<file>.enc','rb').read()))"`
4. **Verify integrity**: `sha256sum b.sql.gz` must equal the recorded checksum (S3 object metadata `sha256`).
5. **Restore**: prefer the admin API/`restore_backup()` (it snapshots first). Manual fallback:
   `gunzip -c b.sql.gz | mysql --host=127.0.0.1 --user=$DB_USER $DB_NAME` (MYSQL_PWD in env).
6. **Restart + health-check**: `systemctl restart exzelon-api exzelon-web` then
   `curl -fsS https://ra.partnerwithus.tech/health` (expects DB-ok). Watch Sentry for new errors.
7. **Post-restore**: confirm the lifespan idempotent migrations ran (schema up to date), verify a
   tenant login + a dashboard load, and re-point DNS if the host changed.

## Bad-deploy rollback (no data loss)
`cd /opt/exzelon-ra-agent && git checkout <last-good-sha> && (cd frontend && npm run build) && systemctl restart exzelon-api exzelon-web`
then health-check. (Automated `rollback.sh` is tracked as ELR-025.)

## Drill cadence
Run a **quarterly restore drill** into a scratch DB from the latest offsite backup; record the
measured RTO and any gaps here.
