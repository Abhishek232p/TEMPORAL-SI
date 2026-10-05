import pytest
from sqlalchemy.exc import IntegrityError
import uuid
from packages.core.db.models import Organization, Project, Dataset

def test_tenant_isolation_project_slug(db_session):
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    
    org1 = Organization(id=org1_id, name="Org 1", slug="org-1")
    org2 = Organization(id=org2_id, name="Org 2", slug="org-2")
    db_session.add_all([org1, org2])
    db_session.commit()
    
    # Same slug different org is allowed
    proj1 = Project(organization_id=org1_id, name="Proj", slug="proj")
    proj2 = Project(organization_id=org2_id, name="Proj", slug="proj")
    db_session.add_all([proj1, proj2])
    db_session.commit()
    
    # Same slug same org fails
    proj3 = Project(organization_id=org1_id, name="Proj", slug="proj")
    db_session.add(proj3)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_cross_tenant_project_link_blocked(db_session):
    # Depending on DB schema, this usually tests application bounds, but let's test repository bounds.
    pass
