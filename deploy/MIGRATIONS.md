# Database migrations — Alembic (ELR-026)

Schema changes now go through **Alembic**, not ad-hoc `ALTER TABLE` blocks in
`main.py`. This gives every change a versioned, reversible history.

## Layout
- `backend/alembic.ini` — config (`script_location = migrations`).
- `backend/migrations/env.py` — imports **all** models via `app.db.models`, so
  `Base.metadata` is complete; DB URL comes from the `DATABASE_URL` env var if set,
  else `settings.DATABASE_URL`.
- `backend/migrations/versions/0001_baseline.py` — baseline = the full current
  schema (built from the models via `create_all`, so it matches the app exactly).

## First-time adoption per environment
- **Fresh DB**: `alembic upgrade head` — creates everything.
- **Existing DB** (schema already present via the legacy lifespan migrations):
  `alembic stamp 0001_baseline` — records the baseline as applied WITHOUT re-creating
  tables. Do this once on prod before the first real Alembic revision.

## Adding a change (going forward)
1. Edit the SQLAlchemy model(s).
2. `cd backend && alembic revision -m "add X to Y"` (or `--autogenerate`, then
   review — autogenerate misses some server_defaults/enums, so always check).
3. Fill in `upgrade()` / `downgrade()` with explicit `op.*` calls.
4. `alembic upgrade head` locally to test; `alembic downgrade -1` to verify rollback.
5. Deploy runs `alembic upgrade head`.

## Transition note (legacy `main.py` block)
The large idempotent migration block in `main.py`'s lifespan is **kept as a safety
net** for now — it is idempotent and harmless once the schema exists. Retiring it
(moving each remaining ALTER into a discrete Alembic revision, then deleting the
block) is a follow-up (ELR-026b) to be done carefully, one migration at a time, so
prod is never left half-migrated. Until then: **new** changes use Alembic; do not
add new ALTERs to `main.py`.
