from dataclasses import dataclass
from uuid import UUID
from typing import Optional

@dataclass
class AuthContext:
    user_id: UUID
    organization_id: UUID
    role: str
    is_system: bool = False
