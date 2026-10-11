import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from applications.api.routers import auth as auth_router
from packages.core.auth.password import hash_password, verify_password
from packages.core.auth.tokens import create_access_token, decode_access_token
from packages.core.db.models import Base, User
from packages.core.db.session import get_db

def test_password_hashing():
    password = "super_secure_password"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)

def test_jwt_token_creation_and_decoding():
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    data = {"sub": user_id, "org": org_id, "role": "ADMIN"}
    
    token = create_access_token(data)
    assert token is not None
    
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == user_id
    assert decoded["org"] == org_id
    assert decoded["role"] == "ADMIN"
    assert "exp" in decoded

def test_jwt_invalid_token():
    assert decode_access_token("invalid.token.string") is None


def test_login_rejects_invalid_password():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router.router)

    db = TestingSessionLocal()
    existing_user = User(
        id=uuid.uuid4(),
        email="alice@example.com",
        password_hash=hash_password("correct-password"),
        status="ACTIVE",
    )
    legacy_user = User(
        id=uuid.uuid4(),
        email="legacy@example.com",
        password_hash="hashed_legacy-password",
        status="ACTIVE",
    )
    db.add_all([existing_user, legacy_user])
    db.commit()
    db.close()

    client = TestClient(app)
    response = client.post("/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"

    response = client.post("/v1/auth/login", json={"email": "alice@example.com", "password": "correct-password"})
    assert response.status_code == 200

    response = client.post("/v1/auth/login", json={"email": "legacy@example.com", "password": "legacy-password"})
    assert response.status_code == 200
    db = TestingSessionLocal()
    migrated_user = db.query(User).filter(User.email == "legacy@example.com").one()
    assert migrated_user.password_hash.startswith("$2")
    assert verify_password("legacy-password", migrated_user.password_hash)
    db.close()


def test_registration_hashes_password_and_login_authenticates_account():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router.router)

    client = TestClient(app)
    response = client.post(
        "/v1/auth/register",
        json={"email": "new@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 201

    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "new@example.com").one()
    assert verify_password("a-strong-password", user.password_hash)
    db.close()

    response = client.post(
        "/v1/auth/login",
        json={"email": "new@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 200


def test_login_does_not_create_accounts_for_unknown_emails():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router.router)

    response = TestClient(app).post(
        "/v1/auth/login",
        json={"email": "unknown@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 401

    db = TestingSessionLocal()
    assert db.query(User).count() == 0
    db.close()


def test_register_creates_account_and_rejects_duplicate_email():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth_router.router)
    client = TestClient(app)

    response = client.post(
        "/v1/auth/register",
        json={"email": "  New.User@example.com ", "password": "a-strong-password"},
    )
    assert response.status_code == 201
    assert response.json()["user_id"]
    assert response.json()["access_token"]

    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "new.user@example.com").one()
    assert verify_password("a-strong-password", user.password_hash)
    db.close()

    response = client.post(
        "/v1/auth/register",
        json={"email": "new.user@example.com", "password": "another-strong-password"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists. Sign in instead."


def test_register_requires_password_of_at_least_eight_characters():
    app = FastAPI()
    app.include_router(auth_router.router)
    response = TestClient(app).post(
        "/v1/auth/register",
        json={"email": "new@example.com", "password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Password must be at least 8 characters"
