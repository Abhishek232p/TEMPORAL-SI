from sqlalchemy.orm import Session
from uuid import UUID
from packages.core.db.models import Organization, Project

class ProjectRepository:
    def __init__(self, session: Session, organization_id: UUID):
        self.session = session
        self.organization_id = organization_id

    def create(self, name: str, slug: str) -> Project:
        project = Project(organization_id=self.organization_id, name=name, slug=slug)
        self.session.add(project)
        self.session.flush()
        return project

    def get_by_id(self, project_id: UUID) -> Project:
        return self.session.query(Project).filter_by(
            id=project_id, 
            organization_id=self.organization_id
        ).first()
