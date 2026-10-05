# ADR-002: PostgreSQL as Primary Datastore

**STATUS**: Accepted
**CONTEXT**: The system needs to store relational data, metadata, and graph edges.
**DECISION**: Use PostgreSQL as the primary database for relational and graph edge storage in Phase 002.
**CONSEQUENCES**: Avoids operational overhead of maintaining a dedicated graph DB initially. Graph queries will use recursive CTEs if necessary.
