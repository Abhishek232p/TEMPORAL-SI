# Database Deletion Policy

- Cascading deletes (`ON DELETE CASCADE`) are restricted to safe hierarchies (e.g., `PredictionInterval` cascades on `ForecastPoint` deletion).
- Immutable artifacts (`dataset_versions`, `model_versions`, `proof_objects`) use `RESTRICT` to prevent destruction of historical lineage.
