# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Data science and ML teams validating time-series datasets and forecasting workflows.

## Product Purpose

The Temporal Intelligence Platform helps teams evaluate time-series data quality and temporal leakage risks before relying on forecasting workflows. Success means teams can inspect a dataset, run repeatable checks, and understand the findings and their evidence.

## Positioning

Unlike a generic forecasting endpoint or chat assistant, the platform centers on dataset-level quality validation and temporal causal-safety analysis, with persisted reports and inspectable findings.

## Operating Context

Users organize work by organization and project, create datasets, upload versioned CSV or Parquet artifacts, and run profiling, quality, and causal-safety analyses on dataset versions.

## Capabilities and Constraints

The repository implements organization/project/dataset management, dataset version uploads, dataset profiling, data quality reports, and temporal causal-safety reports. Causal-safety checks include statistical heuristics as well as structural checks; heuristic findings indicate risk for review and do not prove causality. Results are scoped to the authenticated organization. Production database persistence and artifact durability depend on deployment configuration.

## Evidence on Hand

The API, analysis engines, architecture documentation, and automated tests are present in the repository. No customer endorsements, benchmark results, or external proof assets are documented; do not invent them.

## Product Principles

- Make uncertainty and evidence visible.
- Keep analysis reproducible and tied to a dataset version.
- Distinguish structural violations from statistical suspicions.
- Protect organization boundaries.
- Do not imply guaranteed forecast accuracy or causal proof.

