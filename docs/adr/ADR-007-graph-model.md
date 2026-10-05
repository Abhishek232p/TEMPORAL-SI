# ADR-007: Logical Graph Model

**STATUS**: Accepted
**CONTEXT**: Entities in the platform (datasets, features, models, forecasts) have complex interdependencies.
**DECISION**: Abstract these dependencies as a graph with typed nodes and explicit edge enums (e.g., `DERIVED_FROM`, `EVALUATED_BY`).
**CONSEQUENCES**: Enables querying lineage and impact analysis. Backed initially by Postgres tables.
