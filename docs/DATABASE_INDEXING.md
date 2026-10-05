# Database Indexing

- **Primary Keys**: B-Tree indices on UUID fields.
- **Tenant lookups**: Composite indices on `(organization_id, created_at)` for high-frequency list endpoints.
- **Graph lookups**: Indices on `source_node_id` and `target_node_id` to rapidly resolve DAG lineages.
