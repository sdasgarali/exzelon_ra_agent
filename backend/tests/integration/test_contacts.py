"""Integration tests for contacts endpoints."""
import pytest
from app.db.models.contact import ContactDetails, PriorityLevel


class TestContactsEndpoints:
    """Tests for contacts API endpoints."""

    @pytest.fixture
    def sample_contact(self, db_session):
        """Create a sample contact for testing."""
        contact = ContactDetails(
            client_name="Test Company",
            first_name="John",
            last_name="Doe",
            title="HR Manager",
            email="john.doe@testcompany.com",
            location_state="CA",
            phone="+1-555-123-4567",
            source="mock",
            priority_level=PriorityLevel.P3_HR_MANAGER,
        )
        db_session.add(contact)
        db_session.commit()
        db_session.refresh(contact)
        return contact

    def test_list_contacts(self, client, auth_headers, sample_contact):
        """Test listing contacts returns paginated response."""
        response = client.get("/api/v1/contacts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "pages" in data
        assert len(data["items"]) >= 1

    def test_get_contact(self, client, auth_headers, sample_contact):
        """Test getting a specific contact."""
        response = client.get(
            f"/api/v1/contacts/{sample_contact.contact_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["contact_id"] == sample_contact.contact_id
        assert data["email"] == sample_contact.email

    def test_create_contact(self, client, auth_headers):
        """Test creating a new contact."""
        response = client.post(
            "/api/v1/contacts",
            headers=auth_headers,
            json={
                "client_name": "New Company",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@newcompany.com",
                "title": "Recruiter"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "jane.smith@newcompany.com"
        assert data["first_name"] == "Jane"

    def test_create_duplicate_contact(self, client, auth_headers, sample_contact):
        """Test creating a contact with duplicate email fails."""
        response = client.post(
            "/api/v1/contacts",
            headers=auth_headers,
            json={
                "client_name": "Another Company",
                "first_name": "Different",
                "last_name": "Person",
                "email": sample_contact.email  # Same email
            }
        )
        assert response.status_code == 400

    def test_update_contact(self, client, auth_headers, sample_contact):
        """Test updating a contact."""
        response = client.put(
            f"/api/v1/contacts/{sample_contact.contact_id}",
            headers=auth_headers,
            json={
                "title": "HR Director",
                "validation_status": "valid"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "HR Director"
        assert data["validation_status"] == "valid"

    def test_delete_contact(self, client, auth_headers, sample_contact):
        """Test deleting (archiving) a contact."""
        response = client.delete(
            f"/api/v1/contacts/{sample_contact.contact_id}",
            headers=auth_headers
        )
        assert response.status_code == 204

    def test_filter_contacts_by_client(self, client, auth_headers, sample_contact):
        """Test filtering contacts by client name."""
        response = client.get(
            f"/api/v1/contacts?client_name={sample_contact.client_name[:4]}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    def test_filter_contacts_by_validation_status(self, client, auth_headers, db_session):
        """Test filtering contacts by validation status."""
        contact = ContactDetails(
            client_name="Validated Company",
            first_name="Valid",
            last_name="Contact",
            email="valid@example.com",
            validation_status="valid",
        )
        db_session.add(contact)
        db_session.commit()

        response = client.get(
            "/api/v1/contacts?validation_status=valid",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["validation_status"] == "valid"

    def test_contact_stats(self, client, auth_headers, sample_contact):
        """Test getting contact statistics."""
        response = client.get("/api/v1/contacts/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "by_priority" in data
        assert "by_validation" in data
