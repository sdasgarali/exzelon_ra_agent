# ADR-002: Next.js 14 as Frontend Framework

## Status
Accepted

## Context
We needed a React framework with SSR capabilities, file-based routing, and a good developer experience.

## Decision
Use Next.js 14 with App Router, Tailwind CSS for styling, and Zustand + React Query for state management.

## Consequences
- **Positive**: App Router provides modern React patterns, Tailwind enables rapid UI development
- **Positive**: React Query handles server state caching and synchronization
- **Negative**: App Router is newer, fewer community examples vs Pages Router
- **Trade-off**: Zustand chosen over Redux for simplicity (sufficient for auth state)
