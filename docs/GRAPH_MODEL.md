# Graph Model Architecture

## Graph Edge Abstraction

```mermaid
graph TD
    NODE_A -->|DERIVED_FROM| NODE_B
    NODE_C -->|PREDICTS| NODE_D
    NODE_E -->|EVALUATED_BY| NODE_F
```

## Rules
- Graph abstractions MUST be backed by PostgreSQL for Phase 002.
- Node types MUST include: User, Organization, Project, Dataset, DatasetVersion, Feature, Model, ModelVersion, Experiment, Evaluation, Forecast, Evidence, Proof, Alert, Outcome.
- Edge types MUST be strict enums, not free-form text.
