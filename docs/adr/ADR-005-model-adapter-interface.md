# ADR-005: Model Adapter Interface

**STATUS**: Accepted
**CONTEXT**: The system will support multiple models (baselines, foundation, tree-based). The application should not couple to specific model implementations.
**DECISION**: All models MUST implement a unified `ModelAdapter` interface with standard methods like `predict()`, `metadata()`, `validate_input()`, and `capabilities()`.
**CONSEQUENCES**: Allows swapping or routing between models dynamically without changing orchestration logic.
