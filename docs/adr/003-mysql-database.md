# ADR-003: MySQL as Primary Database

## Status
Accepted (migrated from SQLite)

## Context
Initial development used SQLite for simplicity. As the system grew to handle thousands of leads and contacts, we needed a production-grade RDBMS.

## Decision
Migrate to MySQL 8.x. Keep SQLite support for testing (in-memory) and as a backup option (`DB_TYPE=sqlite`).

## Consequences
- **Positive**: Better concurrency, full-text search, proper connection pooling
- **Positive**: Industry standard, excellent tooling and backup options
- **Negative**: Additional infrastructure dependency
- **Trade-off**: Using pymysql driver (pure Python) over mysqlclient (C extension) for easier cross-platform support
