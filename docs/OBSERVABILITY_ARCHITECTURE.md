# Observability Architecture

## Rules
- All requests MUST have a trace ID.
- Monitoring MUST track: request latency, job latency, model latency, error rate, forecast error, data drift, model drift, calibration degradation, queue health, resource usage.
- Error codes MUST be explicit and typed.
