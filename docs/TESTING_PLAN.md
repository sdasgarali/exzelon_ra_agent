# NeuraLeads AI Agent - Testing Plan

## Document Information
- **Version**: 1.0
- **Date**: 2026-01-18
- **Author**: Claude Code
- **Status**: Complete

---

## 1. Executive Summary

This document outlines the comprehensive testing strategy for the NeuraLeads AI Agent. The testing covers all modules including lead sourcing, contact enrichment, email validation, outreach management, and the admin panel.

## 2. Test Scope

### 2.1 In Scope
- Authentication and Authorization (RBAC)
- Lead Management (CRUD operations)
- Client Management (CRUD operations)
- Contact Management (CRUD operations)
- Email Validation Pipeline
- Outreach Pipeline
- Dashboard and KPIs
- Settings Management
- Provider Adapters (Mock)

### 2.2 Out of Scope
- Real provider API integration testing (requires API keys)
- Load/Performance testing
- Security penetration testing

## 3. Test Types

### 3.1 Unit Tests
Located in: `backend/tests/unit/`

| Test File | Description | Test Count |
|-----------|-------------|------------|
| test_adapters.py | Tests for all provider adapters | 20+ |

**Key Test Cases:**
- Mock Job Source Adapter
  - test_test_connection
  - test_fetch_jobs_returns_list
  - test_fetch_jobs_with_filters
  - test_job_has_required_fields
- Mock Contact Discovery Adapter
  - test_search_contacts_returns_list
  - test_search_contacts_respects_limit
  - test_contact_has_required_fields
- Mock Email Validation Adapter
  - test_validate_email_returns_result
  - test_validate_email_normalizes_email
  - test_validate_bulk_returns_list
- Mock Email Send Adapter
  - test_send_email_success
  - test_send_bulk_respects_rate_limit

### 3.2 Integration Tests
Located in: `backend/tests/integration/`

| Test File | Description | Test Count |
|-----------|-------------|------------|
| test_auth.py | Authentication endpoints | 7 |
| test_leads.py | Lead management endpoints | 12 |
| test_contacts.py | Contact management endpoints | 10 |

**Key Test Cases:**
- Authentication
  - test_register_user
  - test_login_success
  - test_login_wrong_password
  - test_get_me_authenticated
- Leads
  - test_list_leads
  - test_list_leads_pagination
  - test_create_lead
  - test_update_lead
  - test_delete_lead
  - test_filter_leads_by_status
- Contacts
  - test_list_contacts
  - test_create_contact
  - test_update_contact
  - test_filter_contacts_by_validation_status

### 3.3 End-to-End Tests
Located in: `backend/tests/e2e/`

| Test File | Description | Test Count |
|-----------|-------------|------------|
| test_workflow.py | Complete workflow tests | 10+ |

**Key Test Cases:**
- test_complete_workflow (Happy Path)
- test_client_lifecycle
- test_user_roles_access
- test_pipeline_runs_listing
- test_settings_management
- test_dashboard_tabs

### 3.4 Negative Tests
- test_invalid_token
- test_missing_required_fields
- test_invalid_email_format
- test_delete_nonexistent_resource
- test_update_nonexistent_resource

## 4. Test Data

### 4.1 Test Users

| Email | Password | Role | Purpose |
|-------|----------|------|---------|
| admin@exzelon.com | Admin@123 | Admin | Full access testing |
| operator@exzelon.com | Operator@123 | Operator | Pipeline operations |
| viewer@exzelon.com | Viewer@123 | Viewer | Read-only access |
| testclient@example.com | TestClient@123 | Operator | Client user testing |

### 4.2 Test Companies

| Company Name | Industry | Size |
|--------------|----------|------|
| Acme Healthcare Corp | Healthcare | 51-200 |
| MediCare Solutions Inc | Healthcare | 1-50 |
| TechManufacturing LLC | Manufacturing | 201-500 |
| Industrial Logistics Corp | Logistics | 51-200 |
| Retail Giants Co | Retail | 501-1000 |

### 4.3 Test Leads

| Company | Job Title | State | Source |
|---------|-----------|-------|--------|
| Acme Healthcare Corp | Warehouse Manager | CA | linkedin |
| MediCare Solutions Inc | Operations Manager | TX | glassdoor |
| TechManufacturing LLC | Production Supervisor | OH | linkedin |

### 4.4 Test Contacts

| Name | Title | Email | Priority |
|------|-------|-------|----------|
| John Smith | HR Manager | john.smith@acmehealthcare.com | P3 |
| Jane Doe | Recruiter | jane.doe@acmehealthcare.com | P2 |
| Michael Johnson | Operations Director | michael.johnson@medicare.com | P4 |

## 5. Test Execution

### 5.1 Prerequisites
1. Python 3.11+ installed
2. All dependencies installed: `pip install -r requirements.txt`
3. pytest-html installed for reports: `pip install pytest-html`

### 5.2 Running Tests

```bash
# Navigate to project root
cd RA-01182026

# Run all tests
python scripts/run_tests.py --all --report

# Run specific test types
python scripts/run_tests.py --unit
python scripts/run_tests.py --integration
python scripts/run_tests.py --e2e

# Run with verbose output
python scripts/run_tests.py --all --verbose --report
```

### 5.3 Direct pytest commands

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_adapters.py -v

# Run specific test
pytest tests/integration/test_auth.py::TestAuthEndpoints::test_login_success -v
```

## 6. UAT Test Scenarios

### 6.1 Scenario 1: Admin User Complete Workflow
1. Login as admin@exzelon.com
2. Navigate to Dashboard
3. View KPIs and statistics
4. Navigate to Leads
5. Create a new lead
6. Navigate to Contacts
7. Create a contact for the lead
8. Navigate to Settings
9. Verify all settings are accessible

### 6.2 Scenario 2: Operator Pipeline Execution
1. Login as operator@exzelon.com
2. Navigate to Pipelines
3. Run Lead Sourcing pipeline
4. Run Contact Enrichment pipeline
5. Run Email Validation pipeline
6. Run Outreach (Mailmerge) pipeline
7. Verify pipeline runs are logged

### 6.3 Scenario 3: Viewer Read-Only Access
1. Login as viewer@exzelon.com
2. Verify Dashboard is accessible
3. Verify Leads list is viewable
4. Verify cannot create/edit/delete leads
5. Verify Settings are not accessible

### 6.4 Scenario 4: Client User EOB Upload Test
1. Login as testclient@example.com
2. Navigate to file upload area
3. Upload test EOB PDF
4. Verify file is processed
5. Verify data is extracted and stored

## 7. Test Acceptance Criteria

### 7.1 Pass Criteria
- All unit tests pass: 100%
- All integration tests pass: 100%
- All E2E tests pass: 100%
- Code coverage: >= 80%
- No critical bugs

### 7.2 Fail Criteria
- Any test failure
- Security vulnerabilities detected
- Data corruption issues
- Authentication bypass possible

## 8. Test Environment

### 8.1 Local Development
- SQLite in-memory database for tests
- Mock adapters for all providers
- No external dependencies required

### 8.2 Docker Environment
- MySQL 8.0
- Redis 7
- Python 3.11
- Node.js 20

## 9. Defect Management

### 9.1 Defect Severity Levels
- **Critical**: System crash, data loss, security breach
- **High**: Major functionality broken, no workaround
- **Medium**: Functionality issue with workaround
- **Low**: Cosmetic issues, minor UX problems

### 9.2 Defect Lifecycle
1. New -> Assigned
2. Assigned -> In Progress
3. In Progress -> Fixed
4. Fixed -> Verified
5. Verified -> Closed

## 10. Test Schedule

| Phase | Activity | Duration |
|-------|----------|----------|
| 1 | Unit Testing | Continuous |
| 2 | Integration Testing | Per feature |
| 3 | E2E Testing | Before release |
| 4 | UAT | Before deployment |
| 5 | Regression | After bug fixes |

## 11. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Lead | | | |
| Dev Lead | | | |
| Product Owner | | | |

---

## Appendix A: Test Commands Quick Reference

```bash
# Seed test data
cd backend
python -m app.db.seed

# Run all tests with report
cd ..
python scripts/run_tests.py --all --report

# Check test coverage
cd backend
pytest tests/ --cov=app --cov-report=html

# Run specific markers
pytest -m unit
pytest -m integration
pytest -m e2e
```

## Appendix B: API Endpoints for Testing

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/auth/login | User login |
| POST | /api/v1/auth/register | User registration |
| GET | /api/v1/leads | List leads |
| POST | /api/v1/leads | Create lead |
| GET | /api/v1/contacts | List contacts |
| POST | /api/v1/contacts | Create contact |
| GET | /api/v1/dashboard/kpis | Get KPIs |
| POST | /api/v1/pipelines/lead-sourcing/run | Run pipeline |
