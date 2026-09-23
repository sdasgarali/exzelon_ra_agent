"""Database base configuration."""
from datetime import datetime
from sqlalchemy import create_engine, event, Column, DateTime, Boolean
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all database models."""

    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower()

    # Common columns for all tables
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)


def configure_sqlite_pragmas(target_engine) -> None:
    """WAL + a busy timeout for SQLite (local dev and tests only).

    WAL lets readers run while a write is in flight, which matters here because the
    APScheduler jobs and HTTP requests share one file. `busy_timeout` makes a blocked
    writer wait rather than fail instantly.

    **Deliberately NOT `BEGIN IMMEDIATE`.** Taking the write lock at the start of every
    transaction does fix the read-then-write race that credit spending hits — but it
    serialises *all* transactions including read-only ones, so a single long-lived
    scheduler session blocks every incoming request. That was measured, not assumed:
    it hung the dev server. SQLite's write-contention problem is scoped to the one code
    path that has it (see `tests/security/test_credit_concurrency.py`), rather than
    paid for by the whole application.

    Production runs MySQL or PostgreSQL, which have real row locks and need none of it.
    """
    @event.listens_for(target_engine, "connect")
    def _sqlite_on_connect(dbapi_connection, _record):  # pragma: no cover - driver glue
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
        except Exception:
            # An in-memory or read-only database may refuse WAL. Not fatal.
            pass
        finally:
            cur.close()


def configure_sqlite_write_locking(target_engine) -> None:
    """`BEGIN IMMEDIATE` on top of the pragmas — for engines that need write serialisation.

    SQLite has no row locks, so `with_for_update()` compiles away and a read-then-write
    transaction (SELECT the balance, UPDATE the balance) races: both connections take a
    SHARED lock on the read, both try to escalate, and SQLite returns SQLITE_BUSY
    *immediately* rather than waiting — waiting could never resolve it, which is why
    `busy_timeout` does not help. Taking the write lock up front makes writers queue.

    This is NOT applied to the application engine: it serialises read-only transactions
    too, and one long-lived session then blocks everything. It exists for tests that
    specifically exercise concurrent crediting, where serialisation is the point.
    """
    configure_sqlite_pragmas(target_engine)

    @event.listens_for(target_engine, "connect")
    def _sqlite_manual_begin(dbapi_connection, _record):  # pragma: no cover - driver glue
        # Hand transaction control to SQLAlchemy so the "begin" hook below governs it.
        # This is also what makes SAVEPOINT work correctly on SQLite.
        dbapi_connection.isolation_level = None

    @event.listens_for(target_engine, "begin")
    def _sqlite_begin_immediate(conn):  # pragma: no cover - driver glue
        conn.exec_driver_sql("BEGIN IMMEDIATE")


# Create engine and session
if settings.DB_TYPE == "sqlite":
    engine = create_engine(
        settings.DATABASE_URL,
        # `timeout` makes a writer queue on a busy database instead of failing at once.
        connect_args={"check_same_thread": False, "timeout": 30},
        echo=False
    )
    configure_sqlite_pragmas(engine)
elif settings.DB_TYPE == "postgresql":
    # Models declare no schema, so they stay portable across sqlite/mysql/postgres.
    # Instead of stamping a schema into the metadata, every connection opens with
    # search_path set — DDL and DML then land in DB_SCHEMA ("app") rather than the
    # PostgREST-exposed `public`. Falls through to public only if the schema is blank.
    _connect_args = {}
    if settings.DB_SCHEMA:
        _connect_args["options"] = f"-csearch_path={settings.DB_SCHEMA},public"
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,      # Supabase's pooler drops idle connections
        pool_recycle=300,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        connect_args=_connect_args,
        echo=False
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
