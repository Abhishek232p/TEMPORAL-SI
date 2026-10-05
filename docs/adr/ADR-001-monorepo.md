# ADR-001: Monorepo Architecture

**STATUS**: Accepted
**CONTEXT**: The Temporal Intelligence Platform requires multiple applications (API, Web, Worker, MCP) and shared packages (core, data-engine, models). Managing these in separate repositories would create versioning and deployment overhead.
**DECISION**: Use a single monorepo for all apps, packages, and models.
**CONSEQUENCES**: Simplifies cross-package refactoring and testing. Requires strict dependency rule enforcement to prevent circular dependencies.
