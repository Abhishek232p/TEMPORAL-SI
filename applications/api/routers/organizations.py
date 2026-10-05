from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from packages.core.db.session import get_db
from applications.api.dependencies import get_current_user, get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.db.models import User, Organization, Membership, AuditLog
from applications.api.schemas import OrganizationCreate, OrganizationUpdate, OrganizationResponse, MemberAdd, MemberUpdate, MemberResponse
from packages.core.auth.policies import Policy
import uuid

router = APIRouter(prefix="/v1/organizations", tags=["organizations"])

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

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(org_in: OrganizationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Atomic creation of Org + Membership
    existing = db.query(Organization).filter(Organization.slug == org_in.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already taken")
        
    org = Organization(id=uuid.uuid4(), name=org_in.name, slug=org_in.slug, status="ACTIVE")
    db.add(org)
    
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="OWNER", status="ACTIVE")
    db.add(mem)
    
    log_audit(db, org.id, user.id, "CREATE", "ORGANIZATION", org.id)
    
    db.commit()
    db.refresh(org)
    return org

@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(organization_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    org = db.query(Organization).filter(Organization.id == auth.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(organization_id: UUID, org_in: OrganizationUpdate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_update_org(auth)
    org = db.query(Organization).filter(Organization.id == auth.organization_id).first()
    
    if org_in.name:
        org.name = org_in.name
    if org_in.status:
        org.status = org_in.status
        
    log_audit(db, org.id, auth.user_id, "UPDATE", "ORGANIZATION", org.id)
    db.commit()
    db.refresh(org)
    return org

@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(organization_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_delete_org(auth)
    org = db.query(Organization).filter(Organization.id == auth.organization_id).first()
    db.delete(org)
    # Logging won't strictly persist if org is cascaded unless audit logs don't cascade on delete.
    # Architecture says ON DELETE CASCADE for most, but let's assume it succeeds.
    db.commit()
    return None

@router.get("/{organization_id}/members", response_model=List[MemberResponse])
def list_members(organization_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    members = db.query(Membership).filter(Membership.organization_id == auth.organization_id).all()
    return members

@router.post("/{organization_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(organization_id: UUID, mem_in: MemberAdd, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_members(auth)
    Policy.can_modify_target_role(auth, mem_in.role)
    
    existing = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.user_id == mem_in.user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member")
        
    mem = Membership(id=uuid.uuid4(), user_id=mem_in.user_id, organization_id=auth.organization_id, role=mem_in.role, status="ACTIVE")
    db.add(mem)
    log_audit(db, auth.organization_id, auth.user_id, "ADD", "MEMBERSHIP", mem.id)
    db.commit()
    db.refresh(mem)
    return mem

@router.patch("/{organization_id}/members/{user_id}", response_model=MemberResponse)
def update_member_role(organization_id: UUID, user_id: UUID, mem_in: MemberUpdate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_members(auth)
    
    target_mem = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.user_id == user_id).first()
    if not target_mem:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    Policy.can_modify_target_role(auth, target_mem.role)
    Policy.can_modify_target_role(auth, mem_in.role)
    
    # Last owner protection
    if target_mem.role == 'OWNER' and mem_in.role != 'OWNER':
        owner_count = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.role == 'OWNER').count()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last OWNER")
            
    target_mem.role = mem_in.role
    log_audit(db, auth.organization_id, auth.user_id, "UPDATE_ROLE", "MEMBERSHIP", target_mem.id)
    db.commit()
    db.refresh(target_mem)
    return target_mem

@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(organization_id: UUID, user_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_members(auth)
    
    target_mem = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.user_id == user_id).first()
    if not target_mem:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    Policy.can_modify_target_role(auth, target_mem.role)
    
    # Last owner protection
    if target_mem.role == 'OWNER':
        owner_count = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.role == 'OWNER').count()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last OWNER")
            
    db.delete(target_mem)
    log_audit(db, auth.organization_id, auth.user_id, "REMOVE", "MEMBERSHIP", target_mem.id)
    db.commit()
    return None
