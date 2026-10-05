from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid

from packages.core.db.session import get_db
from packages.core.db.models import User
from packages.core.auth.tokens import create_access_token
from packages.core.auth.password import hash_password, verify_password

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
    """Authenticate an existing user, or auto-register on first use (launch trial).

    Passwords are stored only as bcrypt hashes; legacy placeholder hashes
    ("hashed_<password>") from earlier development builds are migrated
    transparently to bcrypt on first successful login.
    """
    if not req.email or len(req.password or "") < 6:
        raise HTTPException(status_code=422, detail="Email and a password of at least 6 characters are required")

    email = req.email.lower().strip()
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
        ok = False
        if user.password_hash and user.password_hash.startswith("hashed_"):
            # Legacy dev hash format - verify then migrate to bcrypt.
            if req.password == user.password_hash[len("hashed_"):]:
                user.password_hash = hash_password(req.password)
                db.commit()
                ok = True
        elif user.password_hash:
            try:
                ok = verify_password(req.password, user.password_hash)
            except ValueError:
                ok = False
        if not ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    access_token = create_access_token(data={"sub": str(user.id)})
    return LoginResponse(access_token=access_token, user_id=user.id)
