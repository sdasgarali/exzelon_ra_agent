"""Application constants - eliminates magic numbers from business logic."""

# Multi-tenant
MASTER_TENANT_ID = 1  # The platform-owner tenant; super_admin + this tenant = Global Super Admin

# Pipeline batch limits
ENRICHMENT_BATCH_LIMIT = 200
OUTREACH_BATCH_LIMIT = 100

# Email
SMTP_TIMEOUT = 30
SMTP_RETRY_ATTEMPTS = 3

# CSV export
CSV_EXPORT_BATCH_SIZE = 1000

# Pagination defaults
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# Validation
MAX_CSV_IMPORT_ERRORS_SHOWN = 10

# Cache
DASHBOARD_KPI_CACHE_TTL = 60  # seconds
