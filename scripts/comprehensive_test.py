"""Comprehensive API Test Suite for NeuraLeads AI Cold-Email Automation System."""
import requests
import json
from datetime import datetime
from typing import Dict, List, Any

BASE_URL = "http://localhost:8000/api/v1"

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.errors = []

    def add_pass(self, test_name: str, details: str = ""):
        self.passed.append({"test": test_name, "details": details})
        print(f"[PASS] {test_name}")

    def add_fail(self, test_name: str, expected: Any, actual: Any, details: str = ""):
        self.failed.append({
            "test": test_name,
            "expected": expected,
            "actual": actual,
            "details": details
        })
        print(f"[FAIL] {test_name} - Expected: {expected}, Got: {actual}")

    def add_error(self, test_name: str, error: str):
        self.errors.append({"test": test_name, "error": error})
        print(f"[ERROR] {test_name} - {error}")

    def summary(self) -> Dict:
        total = len(self.passed) + len(self.failed) + len(self.errors)
        return {
            "total": total,
            "passed": len(self.passed),
            "failed": len(self.failed),
            "errors": len(self.errors),
            "pass_rate": f"{(len(self.passed)/total*100):.1f}%" if total > 0 else "0%"
        }

results = TestResults()

def get_admin_token() -> str:
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "admin@exzelon.com", "password": "Admin@123"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    raise Exception(f"Failed to get admin token: {response.text}")

def get_operator_token() -> str:
    """Get operator authentication token."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "operator@exzelon.com", "password": "Operator@123"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    raise Exception(f"Failed to get operator token: {response.text}")

def get_viewer_token() -> str:
    """Get viewer authentication token."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "viewer@exzelon.com", "password": "Viewer@123"}
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    raise Exception(f"Failed to get viewer token: {response.text}")

def headers(token: str) -> Dict:
    """Create authorization headers."""
    return {"Authorization": f"Bearer {token}"}

# ============== AUTHENTICATION TESTS ==============
def test_auth_module():
    print("\n" + "="*60)
    print("MODULE: AUTHENTICATION")
    print("="*60)

    # Test 1: Admin Login
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "admin@exzelon.com", "password": "Admin@123"}
    )
    if response.status_code == 200 and "access_token" in response.json():
        results.add_pass("Auth: Admin Login", "Token received")
    else:
        results.add_fail("Auth: Admin Login", 200, response.status_code, response.text)

    # Test 2: Operator Login
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "operator@exzelon.com", "password": "Operator@123"}
    )
    if response.status_code == 200 and "access_token" in response.json():
        results.add_pass("Auth: Operator Login", "Token received")
    else:
        results.add_fail("Auth: Operator Login", 200, response.status_code)

    # Test 3: Viewer Login
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "viewer@exzelon.com", "password": "Viewer@123"}
    )
    if response.status_code == 200 and "access_token" in response.json():
        results.add_pass("Auth: Viewer Login", "Token received")
    else:
        results.add_fail("Auth: Viewer Login", 200, response.status_code)

    # Test 4: Invalid Password
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "admin@exzelon.com", "password": "WrongPassword"}
    )
    if response.status_code == 401:
        results.add_pass("Auth: Invalid Password Rejected")
    else:
        results.add_fail("Auth: Invalid Password Rejected", 401, response.status_code)

    # Test 5: Non-existent User
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": "nonexistent@example.com", "password": "Test@123"}
    )
    if response.status_code == 401:
        results.add_pass("Auth: Non-existent User Rejected")
    else:
        results.add_fail("Auth: Non-existent User Rejected", 401, response.status_code)

    # Test 6: Get Current User (/me)
    token = get_admin_token()
    response = requests.get(f"{BASE_URL}/auth/me", headers=headers(token))
    if response.status_code == 200 and response.json().get("email") == "admin@exzelon.com":
        results.add_pass("Auth: Get Current User")
    else:
        results.add_fail("Auth: Get Current User", "admin@exzelon.com", response.json().get("email"))

    # Test 7: Unauthenticated Access
    response = requests.get(f"{BASE_URL}/auth/me")
    if response.status_code == 401:
        results.add_pass("Auth: Unauthenticated Access Blocked")
    else:
        results.add_fail("Auth: Unauthenticated Access Blocked", 401, response.status_code)

    # Test 8: Register New User
    test_email = f"test_{datetime.now().strftime('%H%M%S')}@example.com"
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": test_email,
            "password": "Test@123456",
            "full_name": "Test User"
        }
    )
    if response.status_code in [200, 201]:
        results.add_pass("Auth: Register New User", f"Created {test_email}")
    else:
        results.add_fail("Auth: Register New User", "200/201", response.status_code, response.text)

    # Test 9: RBAC - Admin accessing admin endpoint
    token = get_admin_token()
    response = requests.get(f"{BASE_URL}/settings", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Auth: RBAC - Admin Access Settings")
    else:
        results.add_fail("Auth: RBAC - Admin Access Settings", 200, response.status_code)

    # Test 10: RBAC - Viewer restricted from admin endpoints
    token = get_viewer_token()
    response = requests.put(
        f"{BASE_URL}/settings/daily_send_limit",
        headers=headers(token),
        json={"value": 50}
    )
    if response.status_code == 403:
        results.add_pass("Auth: RBAC - Viewer Blocked from Admin Endpoint")
    else:
        results.add_fail("Auth: RBAC - Viewer Blocked from Admin Endpoint", 403, response.status_code)

# ============== LEADS TESTS ==============
def test_leads_module():
    print("\n" + "="*60)
    print("MODULE: LEADS")
    print("="*60)

    token = get_admin_token()

    # Test 1: List Leads
    response = requests.get(f"{BASE_URL}/leads", headers=headers(token))
    if response.status_code == 200 and "items" in response.json():
        results.add_pass("Leads: List All", f"Found {response.json().get('total', 0)} leads")
    else:
        results.add_fail("Leads: List All", 200, response.status_code)

    # Test 2: Create Lead
    test_lead = {
        "client_name": f"Test Company {datetime.now().strftime('%H%M%S')}",
        "job_title": "Test Manager",
        "state": "CA",
        "job_link": f"https://jobs.example.com/test-{datetime.now().strftime('%H%M%S')}",
        "salary_min": 50000,
        "salary_max": 80000,
        "source": "test"
    }
    response = requests.post(f"{BASE_URL}/leads", headers=headers(token), json=test_lead)
    if response.status_code == 201:
        lead_id = response.json().get("lead_id")
        results.add_pass("Leads: Create Lead", f"ID: {lead_id}")
    else:
        results.add_fail("Leads: Create Lead", 201, response.status_code, response.text)
        lead_id = None

    # Test 3: Get Lead by ID
    if lead_id:
        response = requests.get(f"{BASE_URL}/leads/{lead_id}", headers=headers(token))
        if response.status_code == 200 and response.json().get("lead_id") == lead_id:
            results.add_pass("Leads: Get by ID")
        else:
            results.add_fail("Leads: Get by ID", lead_id, response.json().get("lead_id"))

    # Test 4: Update Lead
    if lead_id:
        response = requests.put(
            f"{BASE_URL}/leads/{lead_id}",
            headers=headers(token),
            json={"lead_status": "enriched"}
        )
        if response.status_code == 200 and response.json().get("lead_status") == "enriched":
            results.add_pass("Leads: Update Lead Status")
        else:
            results.add_fail("Leads: Update Lead Status", "enriched", response.json().get("lead_status"))

    # Test 5: Filter by Status
    response = requests.get(
        f"{BASE_URL}/leads?status=new",
        headers=headers(token)
    )
    if response.status_code == 200:
        items = response.json().get("items", [])
        all_new = all(item.get("lead_status") == "new" for item in items)
        if all_new:
            results.add_pass("Leads: Filter by Status", f"Found {len(items)} new leads")
        else:
            results.add_fail("Leads: Filter by Status", "all status=new", "mixed statuses")
    else:
        results.add_fail("Leads: Filter by Status", 200, response.status_code)

    # Test 6: Pagination
    response = requests.get(
        f"{BASE_URL}/leads?page=1&page_size=5",
        headers=headers(token)
    )
    if response.status_code == 200:
        data = response.json()
        if len(data.get("items", [])) <= 5 and "total" in data:
            results.add_pass("Leads: Pagination", f"Page 1 with {len(data['items'])} items")
        else:
            results.add_fail("Leads: Pagination", "<=5 items", len(data.get("items", [])))
    else:
        results.add_fail("Leads: Pagination", 200, response.status_code)

    # Test 7: Leads Stats
    response = requests.get(f"{BASE_URL}/leads/stats", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Leads: Get Stats", str(response.json()))
    else:
        results.add_fail("Leads: Get Stats", 200, response.status_code)

    # Test 8: Get Non-existent Lead
    response = requests.get(f"{BASE_URL}/leads/99999", headers=headers(token))
    if response.status_code == 404:
        results.add_pass("Leads: 404 for Non-existent")
    else:
        results.add_fail("Leads: 404 for Non-existent", 404, response.status_code)

    # Test 9: Delete Lead
    if lead_id:
        response = requests.delete(f"{BASE_URL}/leads/{lead_id}", headers=headers(token))
        if response.status_code in [200, 204]:
            results.add_pass("Leads: Delete Lead")
        else:
            results.add_fail("Leads: Delete Lead", "200/204", response.status_code)

# ============== CLIENTS TESTS ==============
def test_clients_module():
    print("\n" + "="*60)
    print("MODULE: CLIENTS")
    print("="*60)

    token = get_admin_token()

    # Test 1: List Clients
    response = requests.get(f"{BASE_URL}/clients", headers=headers(token))
    if response.status_code == 200 and "items" in response.json():
        results.add_pass("Clients: List All", f"Found {response.json().get('total', 0)} clients")
    else:
        results.add_fail("Clients: List All", 200, response.status_code)

    # Test 2: Create Client
    test_client = {
        "client_name": f"Test Client {datetime.now().strftime('%H%M%S')}",
        "industry": "Healthcare",
        "company_size": "51-200",
        "location_state": "TX"
    }
    response = requests.post(f"{BASE_URL}/clients", headers=headers(token), json=test_client)
    if response.status_code == 201:
        client_id = response.json().get("client_id")
        results.add_pass("Clients: Create Client", f"ID: {client_id}")
    else:
        results.add_fail("Clients: Create Client", 201, response.status_code, response.text)
        client_id = None

    # Test 3: Get Client by ID
    if client_id:
        response = requests.get(f"{BASE_URL}/clients/{client_id}", headers=headers(token))
        if response.status_code == 200:
            results.add_pass("Clients: Get by ID")
        else:
            results.add_fail("Clients: Get by ID", 200, response.status_code)

    # Test 4: Update Client
    if client_id:
        response = requests.put(
            f"{BASE_URL}/clients/{client_id}",
            headers=headers(token),
            json={"status": "inactive"}
        )
        if response.status_code == 200:
            results.add_pass("Clients: Update Client")
        else:
            results.add_fail("Clients: Update Client", 200, response.status_code)

    # Test 5: Filter by Industry
    response = requests.get(
        f"{BASE_URL}/clients?industry=Healthcare",
        headers=headers(token)
    )
    if response.status_code == 200:
        results.add_pass("Clients: Filter by Industry", f"Found {len(response.json().get('items', []))} Healthcare clients")
    else:
        results.add_fail("Clients: Filter by Industry", 200, response.status_code)

    # Test 6: Delete Client
    if client_id:
        response = requests.delete(f"{BASE_URL}/clients/{client_id}", headers=headers(token))
        if response.status_code in [200, 204]:
            results.add_pass("Clients: Delete Client")
        else:
            results.add_fail("Clients: Delete Client", "200/204", response.status_code)

# ============== CONTACTS TESTS ==============
def test_contacts_module():
    print("\n" + "="*60)
    print("MODULE: CONTACTS")
    print("="*60)

    token = get_admin_token()

    # Test 1: List Contacts
    response = requests.get(f"{BASE_URL}/contacts", headers=headers(token))
    if response.status_code == 200 and "items" in response.json():
        results.add_pass("Contacts: List All", f"Found {response.json().get('total', 0)} contacts")
    else:
        results.add_fail("Contacts: List All", 200, response.status_code)

    # Test 2: Create Contact
    test_contact = {
        "client_name": "Acme Healthcare Corp",
        "first_name": "Test",
        "last_name": f"User{datetime.now().strftime('%H%M%S')}",
        "email": f"test{datetime.now().strftime('%H%M%S')}@testcompany.com",
        "title": "HR Manager",
        "location_state": "CA"
    }
    response = requests.post(f"{BASE_URL}/contacts", headers=headers(token), json=test_contact)
    if response.status_code == 201:
        contact_id = response.json().get("contact_id")
        results.add_pass("Contacts: Create Contact", f"ID: {contact_id}")
    else:
        results.add_fail("Contacts: Create Contact", 201, response.status_code, response.text)
        contact_id = None

    # Test 3: Get Contact by ID
    if contact_id:
        response = requests.get(f"{BASE_URL}/contacts/{contact_id}", headers=headers(token))
        if response.status_code == 200:
            results.add_pass("Contacts: Get by ID")
        else:
            results.add_fail("Contacts: Get by ID", 200, response.status_code)

    # Test 4: Update Contact
    if contact_id:
        response = requests.put(
            f"{BASE_URL}/contacts/{contact_id}",
            headers=headers(token),
            json={"validation_status": "valid"}
        )
        if response.status_code == 200:
            results.add_pass("Contacts: Update Contact")
        else:
            results.add_fail("Contacts: Update Contact", 200, response.status_code)

    # Test 5: Filter by Validation Status
    response = requests.get(
        f"{BASE_URL}/contacts?validation_status=valid",
        headers=headers(token)
    )
    if response.status_code == 200:
        results.add_pass("Contacts: Filter by Validation Status")
    else:
        results.add_fail("Contacts: Filter by Validation Status", 200, response.status_code)

    # Test 6: Contacts Stats
    response = requests.get(f"{BASE_URL}/contacts/stats", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Contacts: Get Stats", str(response.json()))
    else:
        results.add_fail("Contacts: Get Stats", 200, response.status_code)

    # Test 7: Delete Contact
    if contact_id:
        response = requests.delete(f"{BASE_URL}/contacts/{contact_id}", headers=headers(token))
        if response.status_code in [200, 204]:
            results.add_pass("Contacts: Delete Contact")
        else:
            results.add_fail("Contacts: Delete Contact", "200/204", response.status_code)

# ============== PIPELINES TESTS ==============
def test_pipelines_module():
    print("\n" + "="*60)
    print("MODULE: PIPELINES")
    print("="*60)

    token = get_admin_token()

    # Test 1: Get Pipeline Runs
    response = requests.get(f"{BASE_URL}/pipelines/runs", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Pipelines: Get Runs History")
    else:
        results.add_fail("Pipelines: Get Runs History", 200, response.status_code)

    # Test 2: Run Contact Enrichment Pipeline (Mock)
    response = requests.post(
        f"{BASE_URL}/pipelines/contact-enrichment/run",
        headers=headers(token),
        json={"lead_ids": [1, 2]}
    )
    if response.status_code in [200, 202]:
        results.add_pass("Pipelines: Run Contact Enrichment")
    else:
        results.add_fail("Pipelines: Run Contact Enrichment", "200/202", response.status_code, response.text)

    # Test 3: Run Email Validation Pipeline (Mock)
    response = requests.post(
        f"{BASE_URL}/pipelines/email-validation/run",
        headers=headers(token),
        json={"contact_ids": [1, 2]}
    )
    if response.status_code in [200, 202]:
        results.add_pass("Pipelines: Run Email Validation")
    else:
        results.add_fail("Pipelines: Run Email Validation", "200/202", response.status_code, response.text)

    # Test 4: Run Outreach Pipeline (Mailmerge)
    response = requests.post(
        f"{BASE_URL}/pipelines/outreach/run",
        headers=headers(token),
        json={"contact_ids": [1, 2], "mode": "mailmerge"}
    )
    if response.status_code in [200, 202]:
        results.add_pass("Pipelines: Run Outreach (Mailmerge)")
    else:
        results.add_fail("Pipelines: Run Outreach (Mailmerge)", "200/202", response.status_code, response.text)

# ============== DASHBOARD TESTS ==============
def test_dashboard_module():
    print("\n" + "="*60)
    print("MODULE: DASHBOARD")
    print("="*60)

    token = get_admin_token()

    # Test 1: Get KPIs
    response = requests.get(f"{BASE_URL}/dashboard/kpis", headers=headers(token))
    if response.status_code == 200:
        data = response.json()
        results.add_pass("Dashboard: Get KPIs", str(data))
    else:
        results.add_fail("Dashboard: Get KPIs", 200, response.status_code)

    # Test 2: Get Trends
    response = requests.get(f"{BASE_URL}/dashboard/trends", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Dashboard: Get Trends")
    else:
        results.add_fail("Dashboard: Get Trends", 200, response.status_code)

    # Test 3: Leads Sourced
    response = requests.get(f"{BASE_URL}/dashboard/leads-sourced", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Dashboard: Leads Sourced")
    else:
        results.add_fail("Dashboard: Leads Sourced", 200, response.status_code)

    # Test 4: Contacts Identified
    response = requests.get(f"{BASE_URL}/dashboard/contacts-identified", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Dashboard: Contacts Identified")
    else:
        results.add_fail("Dashboard: Contacts Identified", 200, response.status_code)

    # Test 5: Client Categories
    response = requests.get(f"{BASE_URL}/dashboard/client-categories", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Dashboard: Client Categories")
    else:
        results.add_fail("Dashboard: Client Categories", 200, response.status_code)

# ============== SETTINGS TESTS ==============
def test_settings_module():
    print("\n" + "="*60)
    print("MODULE: SETTINGS")
    print("="*60)

    token = get_admin_token()

    # Test 1: Get All Settings
    response = requests.get(f"{BASE_URL}/settings", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Settings: Get All", f"Found {len(response.json())} settings")
    else:
        results.add_fail("Settings: Get All", 200, response.status_code)

    # Test 2: Get Single Setting
    response = requests.get(f"{BASE_URL}/settings/daily_send_limit", headers=headers(token))
    if response.status_code == 200:
        results.add_pass("Settings: Get Single", f"Value: {response.json().get('value')}")
    else:
        results.add_fail("Settings: Get Single", 200, response.status_code)

    # Test 3: Update Setting (Admin)
    response = requests.put(
        f"{BASE_URL}/settings/daily_send_limit",
        headers=headers(token),
        json={"value": 35}
    )
    if response.status_code == 200:
        results.add_pass("Settings: Update (Admin)")
    else:
        results.add_fail("Settings: Update (Admin)", 200, response.status_code)

    # Test 4: Restore Original Value
    response = requests.put(
        f"{BASE_URL}/settings/daily_send_limit",
        headers=headers(token),
        json={"value": 30}
    )
    if response.status_code == 200:
        results.add_pass("Settings: Restore Value")
    else:
        results.add_fail("Settings: Restore Value", 200, response.status_code)

# ============== END-TO-END WORKFLOW TEST ==============
def test_e2e_workflow():
    print("\n" + "="*60)
    print("END-TO-END WORKFLOW TEST")
    print("="*60)

    token = get_admin_token()

    # Step 1: Create a new client
    print("\nStep 1: Creating new client...")
    client_data = {
        "client_name": f"E2E Test Corp {datetime.now().strftime('%H%M%S')}",
        "industry": "Manufacturing",
        "company_size": "201-500",
        "location_state": "OH"
    }
    response = requests.post(f"{BASE_URL}/clients", headers=headers(token), json=client_data)
    if response.status_code == 201:
        client_id = response.json().get("client_id")
        client_name = response.json().get("client_name")
        results.add_pass("E2E Step 1: Create Client", f"ID: {client_id}")
    else:
        results.add_fail("E2E Step 1: Create Client", 201, response.status_code)
        return

    # Step 2: Create a lead for this client
    print("Step 2: Creating lead for client...")
    lead_data = {
        "client_name": client_name,
        "job_title": "Production Manager",
        "state": "OH",
        "job_link": f"https://jobs.example.com/e2e-{datetime.now().strftime('%H%M%S')}",
        "salary_min": 60000,
        "salary_max": 85000,
        "source": "linkedin"
    }
    response = requests.post(f"{BASE_URL}/leads", headers=headers(token), json=lead_data)
    if response.status_code == 201:
        lead_id = response.json().get("lead_id")
        results.add_pass("E2E Step 2: Create Lead", f"ID: {lead_id}")
    else:
        results.add_fail("E2E Step 2: Create Lead", 201, response.status_code)
        lead_id = None

    # Step 3: Create contacts for the lead
    print("Step 3: Creating contacts...")
    contacts_created = []
    for i, (fname, lname, title) in enumerate([
        ("John", "Smith", "HR Director"),
        ("Jane", "Doe", "Recruiter"),
        ("Mike", "Johnson", "Talent Acquisition")
    ]):
        contact_data = {
            "client_name": client_name,
            "first_name": fname,
            "last_name": f"{lname}_{datetime.now().strftime('%H%M%S')}",
            "email": f"{fname.lower()}.{lname.lower()}{datetime.now().strftime('%H%M%S')}@e2etest.com",
            "title": title,
            "location_state": "OH"
        }
        response = requests.post(f"{BASE_URL}/contacts", headers=headers(token), json=contact_data)
        if response.status_code == 201:
            contacts_created.append(response.json().get("contact_id"))

    if len(contacts_created) == 3:
        results.add_pass("E2E Step 3: Create Contacts", f"Created {len(contacts_created)} contacts")
    else:
        results.add_fail("E2E Step 3: Create Contacts", 3, len(contacts_created))

    # Step 4: Run email validation on contacts
    print("Step 4: Running email validation...")
    if contacts_created:
        response = requests.post(
            f"{BASE_URL}/pipelines/email-validation/run",
            headers=headers(token),
            json={"contact_ids": contacts_created}
        )
        if response.status_code in [200, 202]:
            results.add_pass("E2E Step 4: Email Validation")
        else:
            results.add_fail("E2E Step 4: Email Validation", "200/202", response.status_code)

    # Step 5: Update lead status to validated
    print("Step 5: Updating lead status...")
    if lead_id:
        response = requests.put(
            f"{BASE_URL}/leads/{lead_id}",
            headers=headers(token),
            json={"lead_status": "validated"}
        )
        if response.status_code == 200:
            results.add_pass("E2E Step 5: Update Lead Status")
        else:
            results.add_fail("E2E Step 5: Update Lead Status", 200, response.status_code)

    # Step 6: Run outreach pipeline (mailmerge)
    print("Step 6: Running outreach pipeline...")
    if contacts_created:
        response = requests.post(
            f"{BASE_URL}/pipelines/outreach/run",
            headers=headers(token),
            json={"contact_ids": contacts_created, "mode": "mailmerge"}
        )
        if response.status_code in [200, 202]:
            results.add_pass("E2E Step 6: Run Outreach")
        else:
            results.add_fail("E2E Step 6: Run Outreach", "200/202", response.status_code)

    # Step 7: Verify dashboard reflects changes
    print("Step 7: Verifying dashboard...")
    response = requests.get(f"{BASE_URL}/dashboard/kpis", headers=headers(token))
    if response.status_code == 200:
        kpis = response.json()
        if kpis.get("total_leads", 0) > 0 and kpis.get("total_contacts", 0) > 0:
            results.add_pass("E2E Step 7: Dashboard Verification", str(kpis))
        else:
            results.add_fail("E2E Step 7: Dashboard Verification", "leads/contacts > 0", str(kpis))
    else:
        results.add_fail("E2E Step 7: Dashboard Verification", 200, response.status_code)

    # Step 8: Cleanup (delete test data)
    print("Step 8: Cleaning up test data...")
    cleanup_success = True
    for contact_id in contacts_created:
        response = requests.delete(f"{BASE_URL}/contacts/{contact_id}", headers=headers(token))
        if response.status_code not in [200, 204]:
            cleanup_success = False
    if lead_id:
        response = requests.delete(f"{BASE_URL}/leads/{lead_id}", headers=headers(token))
        if response.status_code not in [200, 204]:
            cleanup_success = False
    if client_id:
        response = requests.delete(f"{BASE_URL}/clients/{client_id}", headers=headers(token))
        if response.status_code not in [200, 204]:
            cleanup_success = False

    if cleanup_success:
        results.add_pass("E2E Step 8: Cleanup")
    else:
        results.add_fail("E2E Step 8: Cleanup", "All deleted", "Some failed")

def main():
    print("\n" + "="*70)
    print("NEURALEADS AI COLD-EMAIL AUTOMATION SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(f"Test Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}")

    # Check if API is reachable
    try:
        response = requests.get(f"{BASE_URL.replace('/api/v1', '')}/health")
        if response.status_code != 200:
            print("[FAIL] API is not reachable!")
            return
        print("[OK] API is healthy")
    except Exception as e:
        print(f"[FAIL] Cannot connect to API: {e}")
        return

    # Run all test modules
    try:
        test_auth_module()
        test_leads_module()
        test_clients_module()
        test_contacts_module()
        test_pipelines_module()
        test_dashboard_module()
        test_settings_module()
        test_e2e_workflow()
    except Exception as e:
        print(f"\n[WARN] Test execution error: {e}")
        import traceback
        traceback.print_exc()

    # Print Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    summary = results.summary()
    print(f"Total Tests: {summary['total']}")
    print(f"Passed: {summary['passed']} [OK]")
    print(f"Failed: {summary['failed']} [FAIL]")
    print(f"Errors: {summary['errors']} [WARN]")
    print(f"Pass Rate: {summary['pass_rate']}")

    if results.failed:
        print("\n" + "-"*50)
        print("FAILED TESTS DETAILS:")
        print("-"*50)
        for failure in results.failed:
            print(f"  • {failure['test']}")
            print(f"    Expected: {failure['expected']}")
            print(f"    Actual: {failure['actual']}")
            if failure.get('details'):
                print(f"    Details: {failure['details']}")

    print("\n" + "="*70)
    print(f"Test Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    return results

if __name__ == "__main__":
    main()
