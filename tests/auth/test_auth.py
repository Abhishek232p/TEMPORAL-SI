import pytest
import uuid
from packages.core.auth.password import hash_password, verify_password
from packages.core.auth.tokens import create_access_token, decode_access_token

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
