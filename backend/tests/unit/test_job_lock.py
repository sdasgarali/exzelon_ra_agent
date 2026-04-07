"""Tests for MySQL advisory lock helper."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestAdvisoryLock:
    """Test the advisory_lock context manager."""

    @patch("app.core.config.settings")
    def test_sqlite_always_grants(self, mock_settings):
        """SQLite doesn't support advisory locks — should always yield True."""
        mock_settings.DB_TYPE = "sqlite"
        from app.core.job_lock import advisory_lock

        with advisory_lock("test_job") as acquired:
            assert acquired is True

    @patch("app.db.base.SessionLocal")
    @patch("app.core.config.settings")
    def test_mysql_lock_acquired(self, mock_settings, mock_session_cls):
        """When GET_LOCK returns 1, lock is acquired."""
        mock_settings.DB_TYPE = "mysql"
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        from app.core.job_lock import advisory_lock

        with advisory_lock("test_job") as acquired:
            assert acquired is True

        # Verify RELEASE_LOCK was called
        assert mock_db.execute.call_count == 2  # GET_LOCK + RELEASE_LOCK
        mock_db.close.assert_called_once()

    @patch("app.db.base.SessionLocal")
    @patch("app.core.config.settings")
    def test_mysql_lock_not_acquired(self, mock_settings, mock_session_cls):
        """When GET_LOCK returns 0, lock is not acquired."""
        mock_settings.DB_TYPE = "mysql"
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        from app.core.job_lock import advisory_lock

        with advisory_lock("test_job") as acquired:
            assert acquired is False

        # RELEASE_LOCK should NOT be called when not acquired
        assert mock_db.execute.call_count == 1  # Only GET_LOCK
        mock_db.close.assert_called_once()

    @patch("app.db.base.SessionLocal")
    @patch("app.core.config.settings")
    def test_mysql_lock_error_fails_open(self, mock_settings, mock_session_cls):
        """On error, fail-open — yield True so job still runs."""
        mock_settings.DB_TYPE = "mysql"
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.execute.side_effect = Exception("DB connection error")

        from app.core.job_lock import advisory_lock

        with advisory_lock("test_job") as acquired:
            assert acquired is True

        mock_db.close.assert_called_once()

    @patch("app.db.base.SessionLocal")
    @patch("app.core.config.settings")
    def test_lock_name_prefixed(self, mock_settings, mock_session_cls):
        """Lock name should be prefixed with 'exz_'."""
        mock_settings.DB_TYPE = "mysql"
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        from app.core.job_lock import advisory_lock

        with advisory_lock("campaign_processor") as acquired:
            pass

        # Check the GET_LOCK call used the prefixed name
        call_args = mock_db.execute.call_args_list[0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["name"] == "exz_campaign_processor"
