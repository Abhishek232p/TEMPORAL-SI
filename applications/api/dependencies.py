from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from uuid import UUID

from packages.core.db.session import get_db
from packages.core.db.models import User, Membership
from packages.core.auth.tokens import decode_access_token
from packages.core.auth.context import AuthContext

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
        
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise credentials_exception
        
    if user.status != 'ACTIVE':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
        
    return user

def get_auth_context(
    user: User = Depends(get_current_user),
    x_organization_id: str = Header(..., alias="X-Organization-ID"),
    db: Session = Depends(get_db)
) -> AuthContext:
    
    try:
        org_uuid = UUID(x_organization_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization ID format")

    membership = db.query(Membership).filter(
        Membership.user_id == user.id,
        Membership.organization_id == org_uuid
    ).first()
    
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this organization")
        
    if membership.status != 'ACTIVE':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Membership is inactive")
        
    return AuthContext(
        user_id=user.id,
        organization_id=org_uuid,
        role=membership.role
    )
