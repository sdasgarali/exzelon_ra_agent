"""Unit tests for API-key scope rules (app/core/api_key_scopes.py)."""
import pytest

from app.core.api_key_scopes import check_scope, normalize_scopes, parse_scopes_json

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "get"])
@pytest.mark.parametrize("scopes", [["read"], ["write"], ["admin"], [], None])
def test_safe_methods_always_allowed(scopes, method):
    assert check_scope(scopes, method, "/api/v1/leads")[0] is True


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/leads"),
    ("PUT", "/api/v1/leads/5"),
    ("PATCH", "/api/v1/auth/me/notification-preferences"),
    ("DELETE", "/api/v1/leads/5"),
    ("POST", "/api/v1/campaigns/3/activate"),
])
def test_read_scope_blocks_writes(method, path):
    allowed, reason = check_scope(["read"], method, path)
    assert allowed is False
    assert "read-only" in reason


@pytest.mark.parametrize("path", [
    "/api/v1/leads/ai-search",
    "/api/v1/leads/database-search",
    "/api/v1/leads/bulk/enrich/preview",
    "/api/v1/campaigns/7/enrollment-preview",
    "/api/v1/campaigns/compare",
    "/api/v1/spam-check",
])
def test_read_scope_allows_compute_only_posts(path):
    assert check_scope(["read"], "POST", path)[0] is True


def test_read_only_post_allowlist_is_suffix_not_substring():
    # A path that merely contains an allowlisted segment must not pass.
    assert check_scope(["read"], "POST", "/api/v1/leads/ai-search/extra")[0] is False


def test_write_scope_allows_operational_writes():
    for method, path in [("POST", "/api/v1/leads"), ("PUT", "/api/v1/campaigns/1"),
                         ("POST", "/api/v1/pipelines/lead-sourcing/run")]:
        assert check_scope(["write"], method, path)[0] is True


def test_write_scope_blocks_delete():
    allowed, reason = check_scope(["write"], "DELETE", "/api/v1/leads/5")
    assert allowed is False and "cannot delete" in reason


@pytest.mark.parametrize("path", [
    "/api/v1/users", "/api/v1/roles/3", "/api/v1/billing/credits/topup",
    "/api/v1/admin/tenants/2", "/api/v1/auth/change-password", "/api/v1/gdpr/erase",
])
def test_write_scope_blocks_account_admin(path):
    assert check_scope(["write"], "POST", path)[0] is False


def test_admin_scope_allows_everything_but_key_management():
    assert check_scope(["admin"], "DELETE", "/api/v1/leads/5")[0] is True
    assert check_scope(["admin"], "POST", "/api/v1/users")[0] is True


@pytest.mark.parametrize("scopes", [["read"], ["write"], ["admin"]])
@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_no_key_can_manage_keys(scopes, method):
    allowed, reason = check_scope(scopes, method, "/api/v1/integrations/api-keys/4")
    assert allowed is False and "cannot create or revoke" in reason


def test_listing_keys_is_a_read():
    assert check_scope(["read"], "GET", "/api/v1/integrations/api-keys")[0] is True


def test_unknown_or_empty_scopes_fall_back_to_read_only():
    assert check_scope(["superuser"], "POST", "/api/v1/leads")[0] is False
    assert check_scope([], "POST", "/api/v1/leads")[0] is False


def test_trailing_slash_ignored():
    assert check_scope(["read"], "POST", "/api/v1/leads/ai-search/")[0] is True


def test_normalize_and_parse():
    assert normalize_scopes([" Read ", "WRITE", "bogus", 3]) == {"read", "write"}
    assert parse_scopes_json('["read","admin"]') == ["read", "admin"]
    assert parse_scopes_json("not json") == []
    assert parse_scopes_json('{"a": 1}') == []
    assert parse_scopes_json(None) == []


# ── MCP phase 2: more compute-only POSTs reachable with read keys ──────────────

@pytest.mark.parametrize("path", [
    "/api/v1/inbox/threads/abc-123/suggest-reply",
    "/api/v1/campaigns/12/ai-suggest-subjects",
    "/api/v1/templates/score",
    "/api/v1/templates/fixes",
    "/api/v1/templates/apply-fixes",
    "/api/v1/templates/42/preview",
    "/api/v1/email-preview/spam-check",
    "/api/v1/leads/import/google-sheet/preview",
])
def test_read_scope_allows_phase2_compute_only_posts(path):
    assert check_scope(["read"], "POST", path)[0] is True


@pytest.mark.parametrize("path", [
    # These persist data or spend credits, so they stay write-only.
    "/api/v1/email-preview/drafts/5/ai-rewrite",       # rewrites the stored draft
    "/api/v1/email-preview/deliverability-score",      # stores a DNS check + mailbox dns_score
    "/api/v1/email-preview/preview-personalization",   # meters AI credits
    "/api/v1/sequence-generator/generate",             # meters AI credits
    "/api/v1/leads/import/google-sheet",               # the real import
    "/api/v1/templates/42/duplicate",
    "/api/v1/templates/42/activate",
    "/api/v1/inbox/threads/abc/generate-draft",
    "/api/v1/saved-searches",
    "/api/v1/saved-searches/9/execute",  # saves nothing, but searches all tenants today
])
def test_read_scope_still_blocks_persisting_posts(path):
    assert check_scope(["read"], "POST", path)[0] is False


@pytest.mark.parametrize("path", [
    "/api/v1/templates/abc/preview",           # id must be numeric
    "/api/v1/templates/42/preview/extra",
    "/api/v1/v2/templates/42/preview",         # pattern is anchored at the start too
    "/api/v1/campaigns/12/ai-suggest-subjects/apply",
    "/api/v1/inbox/threads/x/suggest-reply/send",
])
def test_phase2_allowlist_is_anchored(path):
    assert check_scope(["read"], "POST", path)[0] is False


def test_phase2_allowlist_is_post_only():
    for method in ("PUT", "PATCH", "DELETE"):
        assert check_scope(["read"], method, "/api/v1/templates/42/preview")[0] is False
        assert check_scope(["read"], method, "/api/v1/campaigns/12/ai-suggest-subjects")[0] is False
