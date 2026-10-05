from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from packages.core.db.session import get_db
from applications.api.dependencies import get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.db.models import Project, AuditLog
from applications.api.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from packages.core.auth.policies import Policy
import uuid

router = APIRouter(prefix="/v1/projects", tags=["projects"])

def log_audit(db, org_id, actor_id, action, resource_type, resource_id):
    audit = AuditLog(
        id=uuid.uuid4(),
        organization_id=org_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id
    )
    db.add(audit)

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(project_in: ProjectCreate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_projects(auth)
    
    # Enforce uniqueness within the organization
    existing = db.query(Project).filter(
        Project.organization_id == auth.organization_id,
        Project.slug == project_in.slug
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Project slug already exists in this organization")
        
    project = Project(
        id=uuid.uuid4(),
        organization_id=auth.organization_id,
        name=project_in.name,
        slug=project_in.slug,
        description=project_in.description,
        status="ACTIVE"
    )
    
    db.add(project)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "PROJECT", project.id)
    db.commit()
    db.refresh(project)
    return project

@router.get("", response_model=List[ProjectResponse])
def list_projects(auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    projects = db.query(Project).filter(Project.organization_id == auth.organization_id).all()
    return projects

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    # Strict boundary: must belong to the requested organization
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return project

@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: UUID, project_in: ProjectUpdate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_projects(auth)
    
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
    if project_in.status is not None:
        project.status = project_in.status
        
    log_audit(db, auth.organization_id, auth.user_id, "UPDATE", "PROJECT", project.id)
    db.commit()
    db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_projects(auth)
    
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db.delete(project)
    log_audit(db, auth.organization_id, auth.user_id, "DELETE", "PROJECT", project.id)
    db.commit()
    return None
