# ADR-001: FastAPI as Backend Framework

## Status
Accepted

## Context
We needed a Python web framework for building REST APIs with async support, automatic OpenAPI documentation, and strong type validation.

## Decision
Use FastAPI with Pydantic for request/response validation and SQLAlchemy for ORM.

## Consequences
- **Positive**: Auto-generated API docs, async support, excellent Python type hints integration, Pydantic validation
- **Positive**: Large ecosystem, active community, production-ready
- **Negative**: Requires Python 3.8+, learning curve for async patterns
- **Trade-off**: Chose sync SQLAlchemy over async (simpler, sufficient for our scale)
