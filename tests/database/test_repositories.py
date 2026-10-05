import pytest
import uuid
from packages.core.repositories.project_repo import ProjectRepository
from packages.core.db.models import Organization

def test_project_repository_tenant_isolation(db_session):
    org1_id = uuid.uuid4()
    org2_id = uuid.uuid4()
    db_session.add(Organization(id=org1_id, name="O1", slug="o1"))
    db_session.add(Organization(id=org2_id, name="O2", slug="o2"))
    db_session.commit()
    
    repo1 = ProjectRepository(db_session, org1_id)
    repo2 = ProjectRepository(db_session, org2_id)
    
    p1 = repo1.create("Project A", "proj-a")
    p2 = repo2.create("Project B", "proj-b")
    
    # repo1 should only see p1
    assert repo1.get_by_id(p1.id) is not None
    assert repo1.get_by_id(p2.id) is None
