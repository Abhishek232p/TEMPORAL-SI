# Tenant Data Isolation

Data isolation is enforced through Composite Foreign Keys and application-level repository bounds.
- A `Dataset` belongs to a `Project` and `Organization`.
- The database schema ensures `organization_id` cascades appropriately.
- Repositories MUST filter by `organization_id` on every query.
