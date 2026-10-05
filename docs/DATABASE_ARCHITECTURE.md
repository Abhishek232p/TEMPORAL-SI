# Database Architecture

The system uses PostgreSQL as the single source of truth for relational state, graph persistence, and configuration. 
Object storage handles large model/data artifacts (referenced by DB).

## Core Principles
- Strict Tenancy: All tenant-owned resources enforce `organization_id` at the database level.
- Graph Projection: Entity tables hold canonical state; `graph_nodes` and `graph_edges` project lineage and relationships.
- Immutability: Artifacts like `dataset_versions` and `model_versions` are treated as append-only/immutable.
