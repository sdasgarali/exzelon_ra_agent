# Troubleshooting Guide

## Common Issues

### Backend Won't Start

**Symptom**: `ModuleNotFoundError` or import errors
```
Solution: Ensure you're in the backend directory and dependencies are installed
cd backend && pip install -r requirements.txt
```

**Symptom**: Database connection refused
```
# Check MySQL is running
mysql -u root -p -e "SELECT 1"

# Verify .env has correct DB settings
cat backend/.env | grep DB_

# Common fix: ensure DB_TYPE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD are set
```

**Symptom**: `OperationalError: Unknown database 'cold_email_ai_agent'`
```sql
-- Create the database
CREATE DATABASE cold_email_ai_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Frontend Won't Start

**Symptom**: `npm run dev` fails with module errors
```bash
cd frontend
rm -rf node_modules .next
npm install
npm run dev
```

**Symptom**: API calls return 401 Unauthorized
- Check that `NEXT_PUBLIC_API_URL` is set correctly in frontend `.env`
- Verify the backend is running on the expected port
- Clear browser localStorage and log in again

### Pipeline Issues

**Symptom**: Lead sourcing returns 0 leads
- Check `JSEARCH_API_KEY` is set in `.env`
- Verify `TARGET_JOB_TITLES` and `TARGET_INDUSTRIES` are configured
- Check API quota on RapidAPI dashboard
- Review pipeline run logs: `GET /api/v1/pipelines/runs`

**Symptom**: Contact enrichment finds no contacts
- Check `CONTACT_PROVIDER` is set to `apollo` or `seamless` (not `mock`)
- Verify the API key for the selected provider
- Check if leads have valid `client_name` values

**Symptom**: Email validation marks everything as invalid
- Check `EMAIL_VALIDATION_PROVIDER` is set correctly
- Verify the validation provider API key
- Test with a known-valid email address first

**Symptom**: Outreach not sending emails
- Check `EMAIL_SEND_MODE` is not `mailmerge` (which only generates files)
- Verify SMTP credentials: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- Check mailbox `warmup_status` is `cold_ready` or `active`
- Verify `emails_sent_today < daily_send_limit`
- Check cooldown: contacts emailed within `COOLDOWN_DAYS` are skipped

### Database Issues

**Symptom**: Column missing after upgrade
```sql
-- Tables created by SQLAlchemy create_all won't ALTER existing tables
-- Run manual migration if needed:
ALTER TABLE table_name ADD COLUMN column_name TYPE DEFAULT value;
```

**Symptom**: Duplicate key errors
```sql
-- Check for duplicates
SELECT job_link, COUNT(*) FROM lead_details GROUP BY job_link HAVING COUNT(*) > 1;
```

### Docker Issues

**Symptom**: Container can't connect to MySQL
- Ensure MySQL container is healthy: `docker-compose ps`
- Check the `DB_HOST` is set to the service name (e.g., `mysql`) not `localhost`
- Wait for MySQL to fully initialize (healthcheck)

**Symptom**: Frontend can't reach backend in Docker
- Check `NEXT_PUBLIC_API_URL` uses the Docker service name or external URL
- Verify port mappings in `docker-compose.yml`

## Performance Troubleshooting

### Slow API Responses
1. Check database connection pool: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`
2. Look for N+1 queries in logs (enable `echo=True` temporarily)
3. Verify indexes exist on frequently queried columns
4. Check if GZip middleware is enabled

### High Memory Usage
1. CSV exports use streaming -- ensure `CSV_EXPORT_BATCH_SIZE` is reasonable
2. Check for large result sets without pagination
3. Monitor background task queue depth

## Getting Help

1. Check pipeline run history: `GET /api/v1/pipelines/runs`
2. Review audit logs: `GET /api/v1/audit`
3. Check application health: `GET /health`
4. Review system docs: `docs/SYSTEM_SOP_AND_WORKING_MECHANISM.md`
