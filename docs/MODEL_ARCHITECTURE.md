# Model Architecture

## Model Adapter and Registry

```mermaid
graph TD
    A[DATA PROFILE] --> B[MODEL ROUTER]
    B --> C[MODEL A]
    B --> D[MODEL B]
    B --> E[MODEL C]
    C --> F[RESULT]
    D --> F
    E --> F
```

## Interface
- Models MUST implement `ModelAdapter` interface.
- Models MUST report capabilities.
- Models MUST be in one of the following states: DRAFT, EXPERIMENTAL, VALIDATED, SHADOW, PRODUCTION, DEPRECATED, RETIRED.
- EXPERIMENTAL models MUST NOT be selected by automated production routing.
