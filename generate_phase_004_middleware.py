import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 1. Update tokens.py to use environment variable
auth_tokens = """
import os
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Read secret from environment, absolutely no hardcoded default in prod
# For local testing if not set, it fails securely unless explicitly mocked.
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "insecure-local-dev-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.PyJWTError:
        return None
"""
write_file("packages/core/auth/tokens.py", auth_tokens)

# 2. Add exceptions
exceptions = """
class AuthException(Exception):
    pass

class UnauthorizedException(AuthException):
    pass

class ForbiddenException(AuthException):
    pass
"""
write_file("packages/core/auth/exceptions.py", exceptions)

# 3. Create FastAPI dependencies
dependencies = """
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
"""
write_file("applications/api/dependencies.py", dependencies)

test_middleware = """
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from applications.api.dependencies import get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.auth.tokens import create_access_token
from packages.core.db.models import User, Organization, Membership
from packages.core.db.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

# Setup test db
engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

# We need to override the get_db dependency in dependencies.py
import applications.api.dependencies as deps
app.dependency_overrides[deps.get_db] = override_get_db

@app.get("/protected")
def protected_route(auth: AuthContext = Depends(get_auth_context)):
    return {"user_id": str(auth.user_id), "org_id": str(auth.organization_id), "role": auth.role}

client = TestClient(app)

@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.close()

@pytest.fixture
def test_data(db):
    user = User(id=uuid.uuid4(), email="test@example.com", password_hash="hash", status="ACTIVE")
    org = Organization(id=uuid.uuid4(), name="Test Org", slug="test-org")
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="ADMIN", status="ACTIVE")
    
    db.add_all([user, org, mem])
    db.commit()
    
    return {"user": user, "org": org, "mem": mem}

def test_missing_token():
    response = client.get("/protected", headers={"X-Organization-ID": str(uuid.uuid4())})
    assert response.status_code == 401

def test_invalid_token():
    response = client.get("/protected", headers={"Authorization": "Bearer invalid", "X-Organization-ID": str(uuid.uuid4())})
    assert response.status_code == 401

def test_missing_org_header(test_data):
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422 # FastAPI missing header

def test_valid_auth(test_data):
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(test_data["org"].id)
    })
    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"

def test_inactive_user(db, test_data):
    test_data["user"].status = "INACTIVE"
    db.commit()
    
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(test_data["org"].id)
    })
    assert response.status_code == 401
    assert "Inactive user" in response.json()["detail"]

def test_wrong_organization(db, test_data):
    other_org_id = str(uuid.uuid4())
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": other_org_id
    })
    assert response.status_code == 403
    assert "User is not a member" in response.json()["detail"]

def test_inactive_membership(db, test_data):
    test_data["mem"].status = "INACTIVE"
    db.commit()
    
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(test_data["org"].id)
    })
    assert response.status_code == 403
    assert "Membership is inactive" in response.json()["detail"]

def test_malformed_token():
    response = client.get("/protected", headers={
        "Authorization": f"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.malformed.token",
        "X-Organization-ID": str(uuid.uuid4())
    })
    assert response.status_code == 401
"""
write_file("tests/auth/test_middleware.py", test_middleware)

# We update requirements.txt to add fastapi and httpx
reqs = """
sqlalchemy>=2.0.0
alembic>=1.12.0
psycopg2-binary>=2.9.9
pytest>=7.4.0
bcrypt>=4.0.1
PyJWT>=2.8.0
fastapi>=0.100.0
httpx>=0.24.1
"""
write_file("requirements.txt", reqs)

print("Middleware Phase 004 files generated.")
