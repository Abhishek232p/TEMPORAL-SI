# Temporal Intelligence Platform

> "We build infrastructure that makes AI predictions on temporal data measurable, explainable, reproducible, and continuously verifiable."

This repository contains the Temporal Intelligence Platform, a production-ready SaaS system for time-series intelligence. 
It differs from standard forecasting endpoints by explicitly focusing on the evaluation, provability, and causal-safety of forecasting methods on users' temporal data.

## System Tenets
1. **Never hide uncertainty:** All predictions must surface confidence intervals.
2. **Never claim guaranteed accuracy:** The system measures accuracy on the user's data.
3. **Reproducibility is paramount:** Every experiment and output must trace back through a verifiable pipeline.
4. **Causal-safety first:** No temporal leakage is permitted in any modeling loop.

## Architecture

Please review [ARCHITECTURE.md](docs/ARCHITECTURE.md) for a complete system graph and design principles.

## Core Services

- `apps/web`: The main frontend interface.
- `apps/api`: Core REST API for programmatic access.
- `apps/mcp-server`: Model Context Protocol server.
- `packages/*`: Reusable business logic, validation, and evaluation engines.
- `models/*`: Adapters and registries for baseline, tree-based, and foundation models.

## Development

See [docker-compose.yml](docker-compose.yml) for local infrastructure.
