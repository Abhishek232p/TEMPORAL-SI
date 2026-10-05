# Security Architecture

## Tenant Graph

```mermaid
graph TD
    A[USER] --> B[MEMBERSHIP]
    B --> C[ORGANIZATION]
    C --> D[PROJECT]
    D --> E[DATASET]
    D --> F[MODEL]
    D --> G[FORECAST]
    D --> H[ALERT]
    D --> I[API KEY]
    D --> J[USAGE]
```

## Security Flow

```mermaid
graph TD
    A[USER] --> B[AUTHENTICATION]
    B --> C[IDENTITY]
    C --> D[MEMBERSHIP]
    D --> E[AUTHORIZATION]
    E --> F[TENANT CONTEXT]
    F --> G[RESOURCE]
    G --> H[ACTION]
    H --> I[AUDIT LOG]
```

## Rules
- Tenant context MUST be resolved securely, never trusted from client payload.
- Permissions MUST be categorized (e.g. PROJECT_READ, DATASET_WRITE).
