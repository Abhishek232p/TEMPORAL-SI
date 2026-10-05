# ADR-003: Redis for Queues and Caching

**STATUS**: Accepted
**CONTEXT**: Workers require a message queue for async jobs. Rate limiting and short-lived locks require fast ephemeral storage.
**DECISION**: Use Redis for queues, rate limiting, and short-lived caching. Redis MUST NOT be used as the system of record.
**CONSEQUENCES**: Provides low-latency ephemeral state, but requires Postgres for durability.
