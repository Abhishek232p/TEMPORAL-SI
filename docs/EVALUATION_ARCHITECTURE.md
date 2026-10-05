# Evaluation Architecture

## Evaluation Flow

```mermaid
graph TD
    A[DATASET VERSION] --> B[TEMPORAL SPLIT]
    B --> C[MODEL VERSION]
    C --> D[FORECAST]
    D --> E[OBSERVED OUTCOME]
    E --> F[METRICS]
    F --> G[CALIBRATION]
    G --> H[EVALUATION RESULT]
    H --> I[MODEL REGISTRY]
```

## Model Promotion Flow

```mermaid
graph TD
    A[EXPERIMENT] --> B[MODEL VERSION]
    B --> C[EVALUATION]
    C --> D[VALIDATION GATE]
    D --> E[SHADOW]
    E --> F[PRODUCTION]
```

## Rules
- Evaluation MUST be independent of model implementation.
- EXPERIMENT models MUST NOT go straight to PRODUCTION without gates.
