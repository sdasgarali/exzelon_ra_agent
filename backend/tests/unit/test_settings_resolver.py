"""Unit tests for the centralized settings resolver."""
import json
import pytest
from app.core.settings_resolver import (
    get_tenant_setting,
    get_tenant_setting_bool,
    set_tenant_setting,
    delete_tenant_setting,
    get_tenant_overrides,
    get_all_tenant_settings,
)
from app.db.models.settings import Settings
from app.db.models.tenant_settings import TenantSettings


pytestmark = pytest.mark.unit


class TestGetTenantSetting:
    """Tests for get_tenant_setting() 4-layer resolution."""

    def test_returns_default_when_nothing_exists(self, db_session, test_tenant):
        result = get_tenant_setting(db_session, "nonexistent_key", tenant_id=test_tenant.tenant_id, default="fallback")
        assert result == "fallback"

    def test_returns_global_setting_when_no_tenant_override(self, db_session, test_tenant):
        db_session.add(Settings(key="test_key", value_json=json.dumps("global_value"), type="string"))
        db_session.flush()

        result = get_tenant_setting(db_session, "test_key", tenant_id=test_tenant.tenant_id)
        assert result == "global_value"

    def test_tenant_override_takes_priority_over_global(self, db_session, test_tenant):
        db_session.add(Settings(key="test_key", value_json=json.dumps("global_value"), type="string"))
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="test_key", value_json=json.dumps("tenant_value")))
        db_session.flush()

        result = get_tenant_setting(db_session, "test_key", tenant_id=test_tenant.tenant_id)
        assert result == "tenant_value"

    def test_global_only_when_no_tenant_id(self, db_session):
        db_session.add(Settings(key="test_key", value_json=json.dumps("global_value"), type="string"))
        db_session.flush()

        result = get_tenant_setting(db_session, "test_key", tenant_id=None)
        assert result == "global_value"

    def test_parses_json_integer(self, db_session, test_tenant):
        db_session.add(Settings(key="num_key", value_json=json.dumps(42), type="integer"))
        db_session.flush()

        result = get_tenant_setting(db_session, "num_key", tenant_id=test_tenant.tenant_id)
        assert result == 42

    def test_parses_json_list(self, db_session, test_tenant):
        db_session.add(Settings(key="list_key", value_json=json.dumps(["a", "b", "c"]), type="list"))
        db_session.flush()

        result = get_tenant_setting(db_session, "list_key", tenant_id=test_tenant.tenant_id)
        assert result == ["a", "b", "c"]

    def test_parses_json_dict(self, db_session, test_tenant):
        val = {"nested": True, "count": 5}
        db_session.add(Settings(key="dict_key", value_json=json.dumps(val), type="json"))
        db_session.flush()

        result = get_tenant_setting(db_session, "dict_key", tenant_id=test_tenant.tenant_id)
        assert result == val

    def test_returns_raw_string_on_json_parse_failure(self, db_session, test_tenant):
        db_session.add(Settings(key="bad_json", value_json="not-valid-json{", type="string"))
        db_session.flush()

        result = get_tenant_setting(db_session, "bad_json", tenant_id=test_tenant.tenant_id)
        assert result == "not-valid-json{"

    def test_different_tenants_see_different_overrides(self, db_session):
        from app.db.models.tenant import Tenant, TenantPlan

        t1 = Tenant(name="T1", slug="t1", plan=TenantPlan.STARTER, max_users=3)
        t2 = Tenant(name="T2", slug="t2", plan=TenantPlan.STARTER, max_users=3)
        db_session.add_all([t1, t2])
        db_session.flush()

        db_session.add(Settings(key="api_key", value_json=json.dumps("global_key"), type="string"))
        db_session.add(TenantSettings(tenant_id=t1.tenant_id, key="api_key", value_json=json.dumps("t1_key")))
        db_session.flush()

        assert get_tenant_setting(db_session, "api_key", tenant_id=t1.tenant_id) == "t1_key"
        assert get_tenant_setting(db_session, "api_key", tenant_id=t2.tenant_id) == "global_key"


class TestGetTenantSettingBool:
    """Tests for get_tenant_setting_bool() boolean coercion."""

    def test_returns_true_for_json_true(self, db_session, test_tenant):
        db_session.add(Settings(key="bool_key", value_json=json.dumps(True), type="boolean"))
        db_session.flush()

        assert get_tenant_setting_bool(db_session, "bool_key", tenant_id=test_tenant.tenant_id) is True

    def test_returns_false_for_json_false(self, db_session, test_tenant):
        db_session.add(Settings(key="bool_key", value_json=json.dumps(False), type="boolean"))
        db_session.flush()

        assert get_tenant_setting_bool(db_session, "bool_key", tenant_id=test_tenant.tenant_id) is False

    def test_returns_default_when_not_found(self, db_session, test_tenant):
        assert get_tenant_setting_bool(db_session, "missing", tenant_id=test_tenant.tenant_id, default=True) is True
        assert get_tenant_setting_bool(db_session, "missing", tenant_id=test_tenant.tenant_id, default=False) is False

    def test_coerces_string_true(self, db_session, test_tenant):
        db_session.add(Settings(key="str_bool", value_json=json.dumps("true"), type="string"))
        db_session.flush()

        assert get_tenant_setting_bool(db_session, "str_bool", tenant_id=test_tenant.tenant_id) is True


class TestSetTenantSetting:
    """Tests for set_tenant_setting() upsert behavior."""

    def test_set_global_creates_new_setting(self, db_session):
        set_tenant_setting(db_session, "new_key", "new_value", tenant_id=None, updated_by="test@test.com")
        db_session.flush()

        row = db_session.query(Settings).filter(Settings.key == "new_key").first()
        assert row is not None
        assert json.loads(row.value_json) == "new_value"
        assert row.updated_by == "test@test.com"

    def test_set_global_updates_existing(self, db_session):
        db_session.add(Settings(key="exist_key", value_json=json.dumps("old"), type="string"))
        db_session.flush()

        set_tenant_setting(db_session, "exist_key", "new", tenant_id=None)
        db_session.flush()

        row = db_session.query(Settings).filter(Settings.key == "exist_key").first()
        assert json.loads(row.value_json) == "new"

    def test_set_tenant_creates_override(self, db_session, test_tenant):
        set_tenant_setting(db_session, "t_key", "t_value", tenant_id=test_tenant.tenant_id, updated_by="admin@test.com")
        db_session.flush()

        row = db_session.query(TenantSettings).filter(
            TenantSettings.tenant_id == test_tenant.tenant_id,
            TenantSettings.key == "t_key",
        ).first()
        assert row is not None
        assert json.loads(row.value_json) == "t_value"

    def test_set_tenant_upserts_existing_override(self, db_session, test_tenant):
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="upsert_key", value_json=json.dumps("v1")))
        db_session.flush()

        set_tenant_setting(db_session, "upsert_key", "v2", tenant_id=test_tenant.tenant_id)
        db_session.flush()

        row = db_session.query(TenantSettings).filter(
            TenantSettings.tenant_id == test_tenant.tenant_id,
            TenantSettings.key == "upsert_key",
        ).first()
        assert json.loads(row.value_json) == "v2"

    def test_set_stores_json_objects(self, db_session, test_tenant):
        val = {"providers": ["a", "b"], "enabled": True}
        set_tenant_setting(db_session, "json_key", val, tenant_id=test_tenant.tenant_id)
        db_session.flush()

        result = get_tenant_setting(db_session, "json_key", tenant_id=test_tenant.tenant_id)
        assert result == val


class TestDeleteTenantSetting:
    """Tests for delete_tenant_setting()."""

    def test_deletes_existing_override(self, db_session, test_tenant):
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="del_key", value_json=json.dumps("val")))
        db_session.flush()

        deleted = delete_tenant_setting(db_session, "del_key", test_tenant.tenant_id)
        assert deleted is True

        row = db_session.query(TenantSettings).filter(
            TenantSettings.tenant_id == test_tenant.tenant_id,
            TenantSettings.key == "del_key",
        ).first()
        assert row is None

    def test_returns_false_when_nothing_to_delete(self, db_session, test_tenant):
        deleted = delete_tenant_setting(db_session, "no_such_key", test_tenant.tenant_id)
        assert deleted is False

    def test_delete_reverts_to_global(self, db_session, test_tenant):
        db_session.add(Settings(key="revert_key", value_json=json.dumps("global"), type="string"))
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="revert_key", value_json=json.dumps("tenant")))
        db_session.flush()

        # Before delete: tenant sees override
        assert get_tenant_setting(db_session, "revert_key", tenant_id=test_tenant.tenant_id) == "tenant"

        delete_tenant_setting(db_session, "revert_key", test_tenant.tenant_id)
        db_session.flush()

        # After delete: tenant sees global
        assert get_tenant_setting(db_session, "revert_key", tenant_id=test_tenant.tenant_id) == "global"


class TestGetTenantOverrides:
    """Tests for get_tenant_overrides()."""

    def test_returns_empty_dict_when_no_overrides(self, db_session, test_tenant):
        assert get_tenant_overrides(db_session, test_tenant.tenant_id) == {}

    def test_returns_all_overrides_for_tenant(self, db_session, test_tenant):
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="k1", value_json=json.dumps("v1")))
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="k2", value_json=json.dumps(42)))
        db_session.flush()

        overrides = get_tenant_overrides(db_session, test_tenant.tenant_id)
        assert overrides == {"k1": "v1", "k2": 42}


class TestGetAllTenantSettings:
    """Tests for get_all_tenant_settings() merge behavior."""

    def test_returns_global_when_no_tenant(self, db_session):
        db_session.add(Settings(key="g1", value_json=json.dumps("gval1"), type="string"))
        db_session.add(Settings(key="g2", value_json=json.dumps("gval2"), type="string"))
        db_session.flush()

        result = get_all_tenant_settings(db_session, tenant_id=None)
        assert result["g1"] == "gval1"
        assert result["g2"] == "gval2"

    def test_merges_tenant_overrides(self, db_session, test_tenant):
        db_session.add(Settings(key="g1", value_json=json.dumps("gval1"), type="string"))
        db_session.add(Settings(key="g2", value_json=json.dumps("gval2"), type="string"))
        db_session.add(TenantSettings(tenant_id=test_tenant.tenant_id, key="g1", value_json=json.dumps("tval1")))
        db_session.flush()

        result = get_all_tenant_settings(db_session, tenant_id=test_tenant.tenant_id)
        assert result["g1"] == "tval1"  # overridden
        assert result["g2"] == "gval2"  # global
