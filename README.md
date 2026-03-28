# NeuraLeads AI Agent

A production-ready cold-email automation system for Research Analysts to identify hiring companies, enrich contacts, validate emails, and manage outreach campaigns.

## Features

- **Lead Sourcing**: Automated job post collection from multiple sources
- **Contact Enrichment**: Decision-maker identification using Apollo/Seamless.ai
- **Email Validation**: Bulk validation via NeverBounce/ZeroBounce
- **Outreach Management**: Mail merge export and programmatic sending
- **Admin Panel**: Full-featured UI for configuration and monitoring
- **Dashboards**: Real-time KPIs including bounce rate, reply rate

## Tech Stack

- **Backend**: Python 3.11+ with FastAPI
- **Frontend**: Next.js 14 with React
- **Database**: MySQL 8+
- **Cache/Queue**: Redis
- **Worker**: Celery

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### 1. Clone and Setup

```bash
# Clone the repository
cd RA-01182026

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
# Required: DB_PASSWORD, SECRET_KEY
# Optional: API keys for providers
```

### 2. Start with Docker

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Access the application
# - Frontend: http://localhost:3000
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/api/docs
```

### 3. Create Admin User

```bash
# Access the API container
docker-compose exec api bash

# Create admin user via API
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "adminpassword", "role": "admin"}'
```

## Local Development

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

## Configuration

All settings can be configured via:
1. Environment variables (`.env` file)
2. Admin Panel Settings page
3. `settings` database table

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| DATA_STORAGE | database | Storage mode: database or files |
| DAILY_SEND_LIMIT | 30 | Max emails per day per mailbox |
| COOLDOWN_DAYS | 10 | Days between emails to same contact |
| MAX_CONTACTS_PER_COMPANY_JOB | 4 | Max contacts per company per job |
| MIN_SALARY_THRESHOLD | 40000 | Minimum salary to include |

## Pipelines

### 1. Lead Sourcing
Fetches job posts from configured sources, normalizes data, and stores in database.

```bash
# Via API
POST /api/v1/pipelines/lead-sourcing/run?sources=linkedin,indeed
```

### 2. Contact Enrichment
Finds decision-makers for leads without contact information.

```bash
# Via API
POST /api/v1/pipelines/contact-enrichment/run
```

### 3. Email Validation
Validates contact emails and updates status.

```bash
# Via API
POST /api/v1/pipelines/email-validation/run
```

### 4. Outreach
Generates mail merge export or sends emails programmatically.

```bash
# Mail merge export
POST /api/v1/pipelines/outreach/run?mode=mailmerge

# Programmatic sending (dry run)
POST /api/v1/pipelines/outreach/run?mode=send&dry_run=true
```

## API Documentation

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- OpenAPI JSON: http://localhost:8000/api/openapi.json

## Business Rules

1. **Target Industries**: Non-IT only (Healthcare, Manufacturing, Logistics, etc.)
2. **Excluded**: IT roles, US staffing/recruitment agencies
3. **Validation**: Only email Valid status contacts
4. **Cooldown**: No email to same contact within 10 days
5. **Per-Company Limit**: Max 4 contacts per company per job
6. **Bounce Rate Target**: Under 2%

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## Project Structure

```
RA-01182026/
├── backend/
│   ├── app/
│   │   ├── api/           # API endpoints
│   │   ├── core/          # Core configuration
│   │   ├── db/            # Database models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic
│   │   │   ├── adapters/  # Provider adapters
│   │   │   └── pipelines/ # Pipeline services
│   │   └── main.py        # FastAPI app
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js pages
│   │   ├── components/    # React components
│   │   └── lib/           # Utilities
│   └── package.json
├── docker/
├── data/                  # Export files
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

Proprietary - Exzelon
