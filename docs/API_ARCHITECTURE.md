# API Architecture

The API exposes domain operations via REST.

## Request Flow

```mermaid
graph TD
    A[HTTP REQUEST] --> B[AUTHENTICATION]
    B --> C[AUTHORIZATION]
    C --> D[VALIDATION]
    D --> E[APPLICATION SERVICE]
    E --> F[DOMAIN / PACKAGE]
    F --> G[REPOSITORY / INFRASTRUCTURE]
```

## Rules
- All protected endpoints MUST resolve `organization_id` from the session.
- API MUST enforce authentication boundaries.
- HTTP logic MUST NOT leak into domain packages.
