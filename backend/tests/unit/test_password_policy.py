"""Tests for password policy enforcement."""
import pytest
from pydantic import ValidationError
from app.schemas.tenant import SignupRequest


pytestmark = pytest.mark.unit


class TestPasswordPolicy:
    """Test password strength validation."""

    def test_valid_password(self):
        req = SignupRequest(
            email="test@example.com",
            password="Test1234!",
            full_name="Test User",
            company_name="Acme Corp",
        )
        assert req.password == "Test1234!"

    def test_rejects_no_uppercase(self):
        with pytest.raises(ValidationError, match="uppercase"):
            SignupRequest(
                email="test@example.com",
                password="test1234!",
                full_name="Test User",
                company_name="Acme Corp",
            )

    def test_rejects_no_number(self):
        with pytest.raises(ValidationError, match="number"):
            SignupRequest(
                email="test@example.com",
                password="TestTest!",
                full_name="Test User",
                company_name="Acme Corp",
            )

    def test_rejects_no_special_char(self):
        with pytest.raises(ValidationError, match="special"):
            SignupRequest(
                email="test@example.com",
                password="Test1234",
                full_name="Test User",
                company_name="Acme Corp",
            )

    def test_rejects_too_short(self):
        with pytest.raises(ValidationError):
            SignupRequest(
                email="test@example.com",
                password="Te1!",
                full_name="Test User",
                company_name="Acme Corp",
            )

    def test_various_special_chars(self):
        specials = ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "_", "-", "+", "="]
        for char in specials:
            req = SignupRequest(
                email="test@example.com",
                password=f"Test1234{char}",
                full_name="Test User",
                company_name="Acme Corp",
            )
            assert char in req.password
