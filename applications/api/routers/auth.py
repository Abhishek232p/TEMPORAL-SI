from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid

from packages.core.db.session import get_db
from packages.core.db.models import User
from packages.core.auth.tokens import create_access_token

router = APIRouter(prefix="/v1/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID

@router.post("/login", response_model=LoginResponse, status_code=200)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    # Simple mock login logic for now: auto-register if not exists
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=req.email,
            password_hash="hashed_" + req.password,
            status="ACTIVE"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # In a real app, verify password hash here
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return LoginResponse(access_token=access_token, user_id=user.id)
