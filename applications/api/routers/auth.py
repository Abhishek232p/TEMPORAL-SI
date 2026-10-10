from fastapi import APIRouter, Depends, HTTPException, status
import hmac
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
import uuid

from packages.core.db.session import get_db
from packages.core.db.models import User
from packages.core.auth.tokens import create_access_token
from packages.core.auth.password import hash_password, verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 UTF-8 bytes or fewer")
        return value

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID

@router.post("/login", response_model=LoginResponse, status_code=200)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(req.password),
            status="ACTIVE"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        stored_hash = user.password_hash or ""
        if stored_hash.startswith("hashed_"):
            password_valid = hmac.compare_digest(stored_hash[7:], req.password)
            if password_valid:
                user.password_hash = hash_password(req.password)
                db.commit()
        else:
            password_valid = bool(stored_hash) and verify_password(req.password, stored_hash)

        if not password_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return LoginResponse(access_token=access_token, user_id=user.id)
