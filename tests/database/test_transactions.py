import pytest
import uuid
from packages.core.db.models import Organization, Project

def test_transaction_rollback(db_session):
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Org", slug="org-tx")
    db_session.add(org)
    
    # Force failure
    try:
        with db_session.begin_nested():
            # Missing fields should cause failure
            proj = Project(organization_id=org_id)
            db_session.add(proj)
    except:
        pass
    
    # Check org still not committed since parent tx not committed, or can rollback fully
    db_session.rollback()
    assert db_session.query(Organization).filter_by(id=org_id).count() == 0
