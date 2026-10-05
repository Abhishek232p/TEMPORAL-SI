# Database Schema

The database consists of typed core entities logically grouped:
- **Identity**: `users`, `organizations`, `memberships`
- **Domain**: `projects`, `datasets`, `dataset_versions`, `data_profiles`, `models`, `model_versions`, `evaluations`, `forecast_runs`
- **Lineage/Proof**: `evidence`, `proof_objects`, `provenance_records`
- **Graph**: `graph_nodes`, `graph_edges`

All entities use UUID primary keys and track `created_at`.
