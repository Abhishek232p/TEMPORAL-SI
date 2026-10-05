# ADR-004: Layered Domain Architecture

**STATUS**: Accepted
**CONTEXT**: Business logic often leaks into HTTP handlers or frontend code.
**DECISION**: Enforce a strict layered architecture: Experience -> Application -> Intelligence -> Data/Model -> Evaluation/Proof -> Infrastructure.
**CONSEQUENCES**: Changes in infrastructure or web frameworks will not require rewriting core domain logic.
