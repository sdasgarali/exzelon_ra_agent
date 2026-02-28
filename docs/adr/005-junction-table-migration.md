# ADR-005: Junction Table for Lead-Contact Relationships

## Status
Accepted (in progress)

## Context
Originally, contacts had a direct `lead_id` FK, creating a one-to-many relationship. In practice, the same contact person may be relevant to multiple leads at the same company.

## Decision
Introduce a `lead_contact_associations` junction table for many-to-many relationships. Keep the legacy `lead_id` FK on contacts for backward compatibility during migration. Queries use both paths (junction + FK) with deduplication.

## Consequences
- **Positive**: Contacts can be shared across leads, reducing duplicate data
- **Positive**: Enables "smart enrichment" -- reuse contacts from company cache
- **Negative**: Dual-path queries are more complex until full migration completes
- **Trade-off**: Gradual migration chosen over big-bang to avoid downtime
