import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

# Production-safe secret: read from env; fall back to the dev-only secret.
SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY",
    "dummy_secret_for_development_change_in_production",
)
if SECRET_KEY == "dummy_secret_for_development_change_in_production":
    # Non-fatal warning so misconfig is visible in deploy logs.
    import warnings
    warnings.warn(
        "JWT_SECRET_KEY is not set - using an INSECURE development key. "
        "Set JWT_SECRET_KEY in your environment before going live.",
        RuntimeWarning,
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc).replace(tzinfo=None) + expires_delta
    else:
        expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.PyJWTError:
        return None
