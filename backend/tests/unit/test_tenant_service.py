"""Tests for tenant model and service."""
import pytest
from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.user import User, UserRole


class TestTenantModel:
    """Test Tenant model and TenantPlan enum."""

    def test_tenant_plan_enum_values(self):
        assert TenantPlan.FREE == "free"
        assert TenantPlan.PRO == "pro"
        assert TenantPlan.MAX == "max"
        assert TenantPlan.CUSTOM == "custom"

    def test_legacy_plan_names_are_aliases(self):
        """The old names repeat existing values, so Python binds them as aliases.

        That keeps every `TenantPlan.ENTERPRISE` call site working through the rename
        without a big-bang edit, while iteration (and therefore the DB enum) still
        yields only the four canonical members.
        """
        assert TenantPlan.STARTER is TenantPlan.FREE
        assert TenantPlan.PROFESSIONAL is TenantPlan.PRO
        assert TenantPlan.ENTERPRISE is TenantPlan.MAX
        assert [p.value for p in TenantPlan] == ["free", "pro", "max", "custom"]

    def test_create_tenant(self, db_session):
        tenant = Tenant(
            name="Test Corp",
            slug="test-corp",
            plan=TenantPlan.FREE,
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)

        assert tenant.tenant_id is not None
        assert tenant.name == "Test Corp"
        assert tenant.slug == "test-corp"
        assert tenant.plan == TenantPlan.FREE
        assert tenant.is_active is True

    def test_create_enterprise_tenant(self, db_session):
        tenant = Tenant(
            name="Enterprise Inc",
            slug="enterprise-inc",
            plan=TenantPlan.ENTERPRISE,
            max_users=999,
            max_mailboxes=999,
            max_contacts=999999,
            max_campaigns=999,
            max_leads=999999,
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)

        assert tenant.plan == TenantPlan.ENTERPRISE
        assert tenant.max_users == 999

    def test_tenant_slug_unique(self, db_session):
        t1 = Tenant(name="A", slug="unique-slug", plan=TenantPlan.STARTER)
        db_session.add(t1)
        db_session.commit()

        t2 = Tenant(name="B", slug="unique-slug", plan=TenantPlan.STARTER)
        db_session.add(t2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestUserTenantRelation:
    """Test User model tenant_id field."""

    def test_create_user_with_tenant(self, db_session):
        tenant = Tenant(name="Corp", slug="corp", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="test@corp.com",
            password_hash="fakehash",
            full_name="Test User",
            role=UserRole.ADMIN,
            tenant_id=tenant.tenant_id,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.tenant_id == tenant.tenant_id
        assert user.is_verified is True

    def test_create_super_admin_without_tenant(self, db_session):
        """Super admin can have tenant_id=NULL (global user)."""
        user = User(
            email="sa@global.com",
            password_hash="fakehash",
            role=UserRole.SUPER_ADMIN,
            tenant_id=None,
            is_verified=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.tenant_id is None
        assert user.role == UserRole.SUPER_ADMIN

    def test_user_defaults_unverified(self, db_session):
        tenant = Tenant(name="T", slug="t", plan=TenantPlan.STARTER)
        db_session.add(tenant)
        db_session.commit()

        user = User(
            email="new@t.com",
            password_hash="fakehash",
            tenant_id=tenant.tenant_id,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.is_verified is False
        assert user.verification_token is None


class TestTenantService:
    """Test tenant service functions."""

    def test_generate_unique_slug(self, db_session):
        from app.services.tenant_service import generate_unique_slug
        slug = generate_unique_slug("Acme Corporation", db_session)
        assert slug == "acme-corporation"

    def test_generate_unique_slug_dedup(self, db_session):
        from app.services.tenant_service import generate_unique_slug
        t = Tenant(name="X", slug="acme-corp", plan=TenantPlan.STARTER)
        db_session.add(t)
        db_session.commit()

        slug = generate_unique_slug("Acme Corp", db_session)
        assert slug == "acme-corp-2"

    def test_generate_unique_slug_strips_special_chars(self, db_session):
        from app.services.tenant_service import generate_unique_slug
        slug = generate_unique_slug("Test & Sons (LLC)", db_session)
        assert slug == "test-sons-llc"

    def test_create_tenant_for_signup(self, db_session):
        """Signup must provision a usable workspace.

        This test previously asserted `max_mailboxes == 0` and `max_contacts == 0` —
        i.e. it locked in the bug that made every self-signup account unable to create
        anything at all. Limits now come from PLAN_MATRIX["free"].
        """
        from app.services.tenant_service import create_tenant_for_signup
        from app.core.plans import PLAN_MATRIX

        tenant = create_tenant_for_signup("My Startup Inc", db_session)
        free = PLAN_MATRIX["free"]

        assert tenant.tenant_id is not None
        assert tenant.name == "My Startup Inc"
        assert tenant.slug == "my-startup-inc"
        assert tenant.plan == TenantPlan.FREE
        assert tenant.max_mailboxes == free.max_mailboxes > 0
        assert tenant.max_contacts == free.max_contacts > 0
        assert tenant.max_campaigns == free.max_campaigns > 0
        assert tenant.max_leads == free.max_leads > 0
        assert tenant.max_lobs == free.max_lobs > 0
        assert tenant.max_users == free.max_users > 0

    def test_signup_tenant_can_actually_create_things(self, db_session):
        """End-to-end of the same regression, through the real limit check."""
        from app.services.tenant_service import create_tenant_for_signup
        from app.api.deps.plan_limits import check_plan_limit

        tenant = create_tenant_for_signup("Usable Co", db_session)
        for resource in ("mailboxes", "contacts", "campaigns", "leads", "lobs", "users"):
            check_plan_limit(db_session, tenant.tenant_id, resource)  # no raise

    def test_create_tenant_slug_collision(self, db_session):
        from app.services.tenant_service import create_tenant_for_signup
        t1 = create_tenant_for_signup("Cool Company", db_session)
        t2 = create_tenant_for_signup("Cool Company", db_session)
        assert t1.slug == "cool-company"
        assert t2.slug == "cool-company-2"
        assert t1.tenant_id != t2.tenant_id
