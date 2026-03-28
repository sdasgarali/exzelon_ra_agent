# Test Automation Guide

## Overview

This guide provides instructions for running the automated test suite for the NeuraLeads AI Agent.

## Prerequisites

1. **Python 3.11+** installed
2. **pip** (Python package manager)
3. **Virtual environment** (recommended)

## Setup

### 1. Create Virtual Environment

```bash
cd RA-01182026/backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt

# Install additional test dependencies
pip install pytest-html pytest-cov
```

## Running Tests

### Quick Start

```bash
# From project root
cd RA-01182026

# Run all tests with report
python scripts/run_tests.py --all --report
```

### Individual Test Suites

```bash
# Unit tests only
python scripts/run_tests.py --unit

# Integration tests only
python scripts/run_tests.py --integration

# End-to-end tests only
python scripts/run_tests.py --e2e
```

### Direct pytest Commands

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html

# Run specific test file
pytest tests/unit/test_adapters.py -v

# Run specific test class
pytest tests/integration/test_auth.py::TestAuthEndpoints -v

# Run specific test
pytest tests/integration/test_auth.py::TestAuthEndpoints::test_login_success -v

# Run with markers
pytest -m unit -v
pytest -m integration -v
pytest -m e2e -v
```

## Test Reports

### HTML Reports
After running with `--report` flag, find reports in:
```
RA-01182026/test_reports/
├── unit_test_report_YYYYMMDD_HHMMSS.html
├── integration_test_report_YYYYMMDD_HHMMSS.html
├── e2e_test_report_YYYYMMDD_HHMMSS.html
├── full_test_report_YYYYMMDD_HHMMSS.html
├── coverage_YYYYMMDD_HHMMSS/
│   └── index.html
└── test_summary_YYYYMMDD_HHMMSS.txt
```

### Coverage Report
```bash
cd backend
pytest tests/ --cov=app --cov-report=html

# Open coverage report
# Windows
start htmlcov/index.html

# Linux/Mac
open htmlcov/index.html
```

## Seed Test Data

```bash
cd backend

# Seed database with test data
python -m app.db.seed
```

This creates:
- Test users (admin, operator, viewer, testclient)
- Sample clients
- Sample leads
- Sample contacts
- Default settings

## Test Configuration

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
python_classes = Test*
addopts = -v --tb=short --strict-markers
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
```

### Environment Variables

For testing, no environment variables are required. Tests use:
- SQLite in-memory database
- Mock adapters for all providers

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest-cov
      - name: Run tests
        run: |
          cd backend
          pytest tests/ -v --cov=app
```

## Troubleshooting

### Common Issues

1. **Import errors**
   ```bash
   # Ensure you're in the right directory
   cd backend
   # Set PYTHONPATH
   export PYTHONPATH=$PWD
   ```

2. **Database errors**
   - Tests use SQLite in-memory, no DB setup needed
   - Each test gets a fresh database

3. **Missing dependencies**
   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-cov pytest-html httpx
   ```

## Test Maintenance

### Adding New Tests

1. Create test file in appropriate directory:
   - `tests/unit/` for unit tests
   - `tests/integration/` for API tests
   - `tests/e2e/` for workflow tests

2. Use appropriate markers:
   ```python
   import pytest

   @pytest.mark.unit
   def test_example():
       pass
   ```

3. Use fixtures from `conftest.py`:
   ```python
   def test_with_auth(client, auth_headers):
       response = client.get("/api/v1/leads", headers=auth_headers)
       assert response.status_code == 200
   ```

### Best Practices

1. Keep tests independent
2. Use fixtures for common setup
3. Test both happy path and error cases
4. Maintain test data in seed.py
5. Update tests when changing API

## Contact

For issues with the test suite, check:
1. GitHub Issues
2. Test documentation in `/docs`
3. Code comments in test files
