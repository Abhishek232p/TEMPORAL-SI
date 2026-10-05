# ADR-009: Async Worker Boundary

**STATUS**: Accepted
**CONTEXT**: Data profiling and forecasting are computationally expensive and slow.
**DECISION**: API handlers MUST NOT block on long-running tasks. They MUST enqueue jobs for a Worker layer.
**CONSEQUENCES**: API remains responsive. Requires state tracking (JobStatus) for clients to poll or receive webhooks.
