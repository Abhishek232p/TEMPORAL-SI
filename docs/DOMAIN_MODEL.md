# Domain Model Architecture

The platform defines strict boundaries for core domain entities.

## Entities
- User
- Organization
- Membership
- Project
- Dataset
- DatasetVersion
- DataSource
- DataConnection
- DataProfile
- DataQualityReport
- Feature
- FeatureRelationship
- Experiment
- Model
- ModelVersion
- ModelEvaluation
- ForecastRun
- ForecastPoint
- PredictionInterval
- AnomalyEvent
- RegimeEvent
- Evidence
- ProofObject
- ProvenanceRecord
- Alert
- APIKey
- UsageRecord
- Subscription
- Invoice
- Webhook
- AuditLog

## Principles
Entities MUST enforce their own internal invariants.
Cross-entity invariants MUST be enforced by application services.
Domain logic MUST NOT rely on external frameworks.
