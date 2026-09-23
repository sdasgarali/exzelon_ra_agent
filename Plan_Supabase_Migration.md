> **CANCELLED 2026-09-23** — user decided not to migrate to Supabase. Prod stays on MySQL. Kept for reference only.

# Plan — MySQL → Supabase (Postgres) Migration

> Status: DRAFT, awaiting approval. Nothing implemented yet.
> Owner: Exzelon RA Agent (NeuraLeads). Created 2026-09-17.

## 0. What we are moving

| Item | Today | After |
|---|---|---|
| Engine | MySQL 8.x, db `exzelon_ra_agent`, user `ra_user` | Supabase Postgres 15+ |
| Driver | `pymysql==1.1.0` (sync only) | `psycopg[binary]` or `psycopg2-binary` |
| ORM | SQLAlchemy 2.0.25 (unchanged) | SQLAlchemy 2.0.25 (unchanged) |
| Schema mgmt | Alembic (`0001_baseline`) + legacy raw-DDL block in `main.py` | Alembic only |
| Tables | 64 tables / 53 model files / 19 Enum columns | same, Postgres-native |
| Live data | ~21,198 contacts, ~235 companies, outreach history | migrated, verified by row-count parity |

Scope is the DATABASE only. Supabase Auth / Storage / Realtime are NOT in scope —
the app keeps its own JWT + Argon2 auth (`core/security.py`) and RBAC.

## 1. Risks found by scoping the code (evidence, not guesses)

### R1 — Collation: MySQL is case-INSENSITIVE, Postgres is case-SENSITIVE  [HIGHEST RISK]
MySQL's `utf8mb4_general_ci` makes `col = 'valid'` match a stored `'Valid'`.
Postgres will not. Proven live: the dashboard audit showed `contact_details.validation_status`
holds BOTH `'Valid'` and `'valid'` in the same column.
- `api/endpoints/contacts.py:85` — `validation_status == <user input>` silently returns
  fewer rows after cutover.
- 7 × `.like(` calls become case-sensitive (76 × `.ilike(` are already safe).
- 21 × `func.lower(` sites are already defensive and unaffected.
**Mitigation:** normalise the data during migration (lowercase the affected status columns)
AND make the comparisons explicitly case-insensitive. Must be done, not optional.

### R2 — Supabase exposes the `public` schema over PostgREST
Anything SQLAlchemy creates in `public` is readable/writable through Supabase's auto REST
API with the project's anon key. With 21k contacts of PII this is a data-breach shape.
**Mitigation:** either enable RLS on all 64 tables (deny-all; our service role bypasses it),
or create the app schema as `app` and keep `public` empty. Decision needed — see §5.

### R3 — Connection pooling
`db/base.py:32` opens `pool_size=20, max_overflow=40` = up to 60 connections.
- Supabase **direct** (`:5432`) is session mode, IPv6-only on new projects, and has a hard
  connection cap by instance size.
- Supabase **pooler** (`:6543`) is PgBouncer transaction mode — IPv4, but breaks server-side
  cursors and prepared statements unless configured (`prepare_threshold=0`).
**Mitigation:** pooler on `:6543` + reduced `pool_size`, and `?sslmode=require`.

### R4 — MySQL-only SQL that will throw on Postgres
- `main.py` — 114 lines of legacy raw DDL: `SHOW COLUMNS`, `INFORMATION_SCHEMA.COLUMNS`,
  `MODIFY COLUMN`, `NOW()`. Already fails on SQLite today (logged as warnings).
- `db/models/job_run.py:5` — `from sqlalchemy.dialects.mysql import LONGTEXT`, 3 columns.
- `core/config.py:80` — `?charset=utf8mb4` in the URL.
**Mitigation:** retire the `main.py` block into Alembic (this is ELR-026b, already on the
backlog); `LONGTEXT` → `Text`; rewrite the URL builder.

### R5 — Type mapping during data load
`TINYINT(1)` → `boolean`, MySQL `ENUM` → Postgres native enum (19 columns), `DATETIME` →
`timestamp`, implicit-cast differences ('' vs NULL), and `AUTO_INCREMENT` → `IDENTITY`
sequences that must be re-synced after load or every INSERT fails on duplicate PK.

## 2. Plan

### Phase A — Make the code dialect-agnostic (no Supabase needed, fully testable)
- [ ] A1. `requirements.txt`: add Postgres driver, keep `pymysql` until cutover.
- [ ] A2. `core/config.py`: `DB_TYPE` gains `"postgresql"`; build a Postgres URL with
      `sslmode=require`; drop `utf8mb4` for that branch. Update `.env.example`.
- [ ] A3. `db/base.py`: Postgres engine branch with Supabase-safe pool settings.
- [ ] A4. `job_run.py`: `LONGTEXT` → portable `Text`.
- [ ] A5. Retire the `main.py` raw-DDL block into Alembic revisions (ELR-026b).
- [ ] A6. Fix R1 at the query layer: case-insensitive comparison on the status columns.
- [ ] A7. Run the FULL backend suite against a local Postgres 15 container — this is the
      gate. Target: same pass count as MySQL (1446+ at last full run).

### Phase B — Schema + data migration (needs Supabase credentials)
- [ ] B1. `alembic upgrade head` against Supabase → creates all 64 tables cleanly.
      (Preferred over pgloader: it gives Postgres-native types instead of translated ones.)
- [ ] B2. Export MySQL prod data per-table to CSV (`mysqldump --tab` or SELECT INTO OUTFILE).
- [ ] B3. Transform: booleans, enums, NULL/'' normalisation, and the R1 case normalisation.
- [ ] B4. Load via `\copy` in FK-dependency order (tenants → users → leads → contacts → …).
- [ ] B5. Re-sync every IDENTITY sequence to `MAX(id)+1`.
- [ ] B6. Verify: per-table row-count parity MySQL vs Supabase + spot-check the dashboard
      numbers (21,198 contacts / 235 companies) end-to-end.

### Phase C — Security + cutover
- [ ] C1. Resolve R2 (RLS deny-all, or non-public schema).
- [ ] C2. Staging run: point a non-prod API at Supabase, exercise login, dashboard,
      contacts grid, campaign send (dry-run), reports.
- [ ] C3. Prod cutover: maintenance window → stop `exzelon-api` → final delta export →
      load → flip `.env` → start → smoke test.
- [ ] C4. Keep MySQL running read-only for N days as rollback. Rollback = flip `.env` back.
- [ ] C5. Update `CLAUDE.md`, `CLAUDE_REFERENCE/deployment.md`, `deploy/MIGRATIONS.md`,
      and the backup/restore runbook (mysqldump → pg_dump).

## 3. Acceptance criteria
1. Full backend suite green on Postgres, zero regressions vs the MySQL baseline.
2. Row-count parity on all 64 tables.
3. Dashboard, contacts grid, campaigns, reports render the same numbers as pre-migration.
4. No table reachable via the Supabase anon key.
5. Documented, tested rollback.

## 4. Non-goals
Supabase Auth, Storage, Realtime, Edge Functions. No schema redesign. No fixing the
dashboard metric defects found on 2026-09-17 (tracked separately) — migrate first, then fix,
so any number change is attributable to one cause.

## 5. Decisions needed before Phase A
- D1. `public` + RLS, or a dedicated non-exposed `app` schema? (affects every table)
- D2. Pooler (`:6543`) or direct (`:5432`)? (affects pool config + IPv4/IPv6)
- D3. Acceptable production downtime for cutover?
- D4. Keep MySQL as hot rollback for how long?

## 6. Credential handling
Supabase DB password / connection string goes into `backend/.env` ONLY (confirmed
gitignored at `.gitignore:37`). Never into `.env.example`, `CLAUDE.md`, memory files,
or any committed file.

## 7. Decisions TAKEN (2026-09-17, recommended by Claude, pending user override)
- **D1 = dedicated `app` schema**, `public` left empty and unexposed. Chosen over RLS
  deny-all because it removes the "someone adds table #65 without RLS" failure mode
  entirely. Cost: `search_path` on connect + Alembic `version_table_schema="app"`.
- **D2 = session pooler, port 5432** (`...pooler.supabase.com`). IPv4 (the direct host is
  IPv6-only on new projects and the VPS may lack IPv6); session mode keeps SQLAlchemy's
  pool, prepared statements and server-side cursors working with no flags.
- **D3 = scheduled maintenance window** (30-90 min, off-hours). Cold outreach is not 24/7;
  dual-write/CDC is days of work and more ways to lose writes than the outage costs.
- **D4 = MySQL kept read-only for 7 days** post-cutover. Rollback = one `.env` flip.

Rationale: the live risk here is silent data divergence (R1 collation), not downtime or
scale. Spend the safety budget on verification + clean rollback; keep mechanics boring.
