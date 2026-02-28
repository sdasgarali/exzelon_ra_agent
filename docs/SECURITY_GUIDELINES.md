# Security Guidelines

## Authentication & Authorization

### JWT Tokens
- Tokens expire after 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES=10080`)
- Tokens are issued on login via `/api/v1/auth/login`
- All API endpoints require a valid Bearer token in the Authorization header
- Never store tokens in localStorage in production; use httpOnly cookies

### Role-Based Access Control (RBAC)
Three roles with cascading permissions:
| Permission | Viewer | Operator | Admin |
|---|:---:|:---:|:---:|
| View leads, contacts, dashboard | Yes | Yes | Yes |
| Run pipelines | No | Yes | Yes |
| Create/edit templates | No | Yes | Yes |
| Bulk operations | No | Yes | Yes |
| Delete/archive records | No | No | Yes |
| Manage users | No | No | Yes |

### Password Security
- Passwords hashed with Argon2 (via `passlib`)
- Minimum password requirements enforced at API level
- Login rate-limited to 5 attempts/minute via SlowAPI

## Data Protection

### Encryption at Rest
- Mailbox passwords encrypted with Fernet symmetric encryption
- Encryption key stored in `ENCRYPTION_KEY` environment variable
- Generate key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Never commit the encryption key to version control

### Sensitive Data Handling
- `.env` files must be in `.gitignore`
- API keys (Apollo, Seamless, etc.) stored only in environment variables
- Database credentials never hardcoded
- CSV exports may contain PII -- handle with care

## API Security

### CORS
- Allowed origins configured via `CORS_ORIGINS` environment variable
- Default: localhost development ports only
- Production: set to your specific frontend domain(s)

### Input Validation
- All request bodies validated via Pydantic schemas with `max_length` constraints
- SQL injection prevented by SQLAlchemy ORM (parameterized queries)
- XSS prevention: DOMPurify on frontend, `html.escape()` on template previews
- Open redirect prevention: URL sanitization on tracking link redirects

### Rate Limiting
- Login endpoint: 5 requests/minute per IP
- Consider adding rate limits to other endpoints in production

### Tracking Endpoints
- HMAC token validation on tracking pixel and link endpoints
- Prevents unauthorized tracking event injection

## Infrastructure Security

### Database
- Use a dedicated database user with minimal privileges (not root)
- Enable SSL for MySQL connections in production
- Regular automated backups with `scripts/backup.sh`

### Deployment
- Always use HTTPS in production (see `deploy/nginx.conf`)
- Set `DEBUG=False` in production
- Change `SECRET_KEY` from default -- use: `openssl rand -hex 32`
- Security headers configured in nginx (X-Frame-Options, HSTS, etc.)

### Docker
- Multi-stage builds minimize image attack surface
- Non-root user in production containers
- No secrets baked into Docker images

## Incident Response

1. **Credential Leak**: Rotate all affected keys immediately, revoke active tokens
2. **Data Breach**: Assess scope, notify affected parties, review audit logs
3. **Unauthorized Access**: Check audit trail (`/api/v1/audit`), revoke sessions
4. **DDoS**: Enable rate limiting, consider Cloudflare or similar CDN

## Audit Trail
- All lead status changes logged to `audit_logs` table
- Query via `/api/v1/audit` endpoints
- Includes: who, what, when, old/new values
