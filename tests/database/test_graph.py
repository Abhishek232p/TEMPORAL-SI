import pytest
from sqlalchemy.exc import IntegrityError
import uuid
from packages.core.db.models import GraphNode, GraphEdge, Organization

def test_graph_node_type_constraint(db_session):
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Org", slug="org")
    db_session.add(org)
    db_session.commit()

    # Valid
    node1 = GraphNode(organization_id=org_id, node_type="DATASET", entity_id=uuid.uuid4())
    db_session.add(node1)
    db_session.commit()

    # Invalid
    node2 = GraphNode(organization_id=org_id, node_type="INVALID_TYPE", entity_id=uuid.uuid4())
    db_session.add(node2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
