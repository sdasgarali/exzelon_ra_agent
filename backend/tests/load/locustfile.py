"""Locust load test for API endpoints.

Usage:
    pip install locust
    cd backend
    locust -f tests/load/locustfile.py --host http://localhost:8000
"""
from locust import HttpUser, task, between


class RAApiUser(HttpUser):
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        """Login to get auth token."""
        response = self.client.post("/api/v1/auth/login", data={
            "username": "admin@example.com",
            "password": "admin123",
        })
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            self.token = "dummy-token"  # Will get 401s but won't crash

    @property
    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def list_leads(self):
        self.client.get("/api/v1/leads?page=1&page_size=50", headers=self.auth_headers)

    @task(3)
    def dashboard_kpis(self):
        self.client.get("/api/v1/dashboard/kpis", headers=self.auth_headers)

    @task(2)
    def list_contacts(self):
        self.client.get("/api/v1/contacts?page=1&page_size=50", headers=self.auth_headers)

    @task(2)
    def lead_stats(self):
        self.client.get("/api/v1/leads/stats", headers=self.auth_headers)

    @task(1)
    def contact_stats(self):
        self.client.get("/api/v1/contacts/stats", headers=self.auth_headers)

    @task(1)
    def list_pipelines(self):
        self.client.get("/api/v1/pipelines/runs", headers=self.auth_headers)

    @task(1)
    def list_templates(self):
        self.client.get("/api/v1/templates", headers=self.auth_headers)

    @task(1)
    def health_check(self):
        self.client.get("/health")
