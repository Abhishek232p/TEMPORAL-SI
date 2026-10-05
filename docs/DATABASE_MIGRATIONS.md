# Database Migrations

We use Alembic for deterministic schema migrations.

- Migrations are version-controlled in `database/migrations/versions`.
- Never modify an already applied migration. Create a new revision.
