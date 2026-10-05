# ADR-010: Temporal Causal Safety

**STATUS**: Accepted
**CONTEXT**: Time-series models frequently suffer from temporal leakage (using future data for past predictions).
**DECISION**: The data engine MUST enforce causal-safety checks (truncate and compare) before data is allowed in model training/evaluation.
**CONSEQUENCES**: Provides strong guarantees against leakage, requiring additional computational overhead during ingestion and validation.
