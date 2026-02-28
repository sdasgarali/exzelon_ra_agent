# ADR-004: Adapter Pattern for External Integrations

## Status
Accepted

## Context
The system integrates with multiple providers for job sourcing, contact discovery, email validation, and email sending. Providers may change or be added.

## Decision
Implement an adapter pattern with abstract base classes. Each provider implements the interface, and provider selection is driven by `.env` configuration. Include `mock` adapters for development/testing.

## Consequences
- **Positive**: Easy to add new providers without changing business logic
- **Positive**: Mock adapters enable offline development and fast testing
- **Positive**: Provider switching requires only an env var change
- **Negative**: Additional abstraction layer adds some complexity
- **Trade-off**: Adapters are synchronous; could be made async for higher throughput
