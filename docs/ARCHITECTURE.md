# Architecture Specification

The complete system is represented as a strict dependency graph. We do not treat features as isolated; each stage depends on the proven validation of the prior stage.

## Dependency Graph

```mermaid
graph TD
    USER --> EXPERIENCE
    EXPERIENCE --> APPLICATION
    APPLICATION --> INTELLIGENCE_ORCHESTRATION
    INTELLIGENCE_ORCHESTRATION --> DATA_ENGINE
    INTELLIGENCE_ORCHESTRATION --> MODEL_ENGINE
    DATA_ENGINE --> DATA_GRAPH
    MODEL_ENGINE --> MODEL_REGISTRY
    DATA_GRAPH --> EVALUATION
    MODEL_REGISTRY --> EVALUATION
    EVALUATION --> PROOF
    PROOF --> MONITORING
    MONITORING --> FEEDBACK
    FEEDBACK --> DATA_ENGINE
```

## System Architecture

```mermaid
graph TD
    A[apps/web] --> B[apps/api]
    B --> C[packages/core]
    C --> D[DATA ENGINE]
    C --> E[MODEL ROUTER]
    C --> F[EVALUATION]
    D --> G[PROOF ENGINE]
    E --> G
    F --> G
    G --> H[DATABASE]
    G --> I[OBJECT STORAGE]
    G --> J[WORKER]
```

## Non-Negotiable Rules
1. The frontend must never directly access protected model infrastructure.
2. The API must enforce tenant isolation and authentication.
3. Every protected object belongs to an `organization_id` resolved from the session.
4. Causal-Safety: Future data must never leak into training or evaluation states.
5. All forecasts require a machine-readable PROOF OBJECT detailing the evidence, confidence, evaluation ID, and provenance hash.
