import logging
import os
from typing import Optional
import jwt
from pydantic import BaseModel, Field

from .config import settings

logger = logging.getLogger(__name__)

class UserPayload(BaseModel):
    user_id: str
    role: Optional[str] = None
    business_id: Optional[str] = None
    is_verified: bool = False
    is_active: bool = False

def get_public_key() -> str:
    """
    Load the RS256 public key from the environment variable JWT_PUBLIC_KEY.
    Handles literal '\n' characters in the string.
    """
    public_key = settings.JWT_PUBLIC_KEY
    if not public_key:
        # Fallback to a placeholder or raise error in production
        logger.warning("JWT_PUBLIC_KEY environment variable is not set!")
        return ""
    
    # Replace literal \n with actual newlines if present
    return public_key.replace("\\n", "\n")

def verify_token_http(token: str) -> UserPayload:
    """
    Verify an RS256 JWT for HTTP requests.
    Raises HTTPException 401 on failure.
    """
    try:
        public_key = get_public_key()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": True}
        )
        
        return UserPayload(
            user_id=payload.get("user_id") or payload.get("sub"),
            role=payload.get("role"),
            business_id=payload.get("business_id"),
            is_verified=payload.get("is_verified", False),
            is_active=payload.get("is_active", False)
        )
    except Exception as e:
        logger.error(f"HTTP Token verification failed: {e}")
        raise ValueError("Invalid or expired token")

def verify_token_ws(token: str) -> Optional[UserPayload]:
    """
    Verify an RS256 JWT for WebSocket connections.
    Returns None on failure instead of raising an exception.
    """
    try:
        public_key = get_public_key()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": True}
        )
        
        return UserPayload(
            user_id=payload.get("user_id") or payload.get("sub"),
            role=payload.get("role"),
            business_id=payload.get("business_id"),
            is_verified=payload.get("is_verified", False),
            is_active=payload.get("is_active", False)
        )
    except Exception as e:
        logger.error(f"WebSocket Token verification failed: {e}")
        return None
