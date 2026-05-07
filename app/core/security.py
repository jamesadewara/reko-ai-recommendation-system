import logging
from typing import Optional, Any
from functools import lru_cache

import httpx
import jwt
from fastapi import Request, HTTPException, Security, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import PyJWTError, ExpiredSignatureError

from app.core.config import settings

logger = logging.getLogger(__name__)


security = HTTPBearer()

_JWKS_CACHE: Optional[dict] = None

async def get_jwks() -> dict:
    """
    Fetch and cache the JWKS from luxe-auth (Django) asynchronously.
    Cached for the lifetime of the process.
    """
    global _JWKS_CACHE
    if _JWKS_CACHE is not None:
        return _JWKS_CACHE

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.JWKS_URL, timeout=10.0)
            response.raise_for_status()
            _JWKS_CACHE = response.json()
            logger.info(f"[Security] JWKS fetched from {settings.JWKS_URL}")
            return _JWKS_CACHE
    except Exception as exc:
        logger.error(f"[Security] Failed to fetch JWKS from {settings.JWKS_URL}: {exc}")
        return {}


async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Verifies an RS256 JWT issued by luxe-auth using remote JWKS.
    Returns the full decoded payload (claims dict) if valid.
    """
    token = credentials.credentials
    jwks = await get_jwks()

    if not jwks or "keys" not in jwks:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service unreachable. Cannot validate token.",
        )

    try:
        header = jwt.get_unverified_header(token)
        rsa_key = {}

        # Match by kid (Key ID) first — most reliable method
        for key in jwks["keys"]:
            if key.get("kid") == header.get("kid"):
                rsa_key = {k: key[k] for k in ("kty", "kid", "use", "n", "e") if k in key}
                break

        # Fallback: use the first key if no kid match (single-key providers)
        if not rsa_key and jwks["keys"]:
            rsa_key = jwks["keys"][0]

        if not rsa_key:
            raise HTTPException(status_code=401, detail="No matching signing key found.")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(rsa_key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},  # Multi-service — no fixed audience
        )

        # Normalise: ensure user_id is always present (some JWT configs use only `sub`)
        if "user_id" not in payload and "sub" in payload:
            payload["user_id"] = payload["sub"]

        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please log in again.")
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token invalid: {str(exc)}")


async def get_token_payload_optional(request: Request) -> Optional[dict]:
    """
    [SMART] Optional Auth: returns JWT claims if token is present and valid, 
    otherwise returns None. Does NOT raise 401/403 if header is missing.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    try:
        from fastapi.security.utils import get_authorization_scheme_param
        scheme, token = get_authorization_scheme_param(auth_header)
        if scheme.lower() != "bearer":
            return None
            
        # Re-use verify logic but handle exceptions silently
        jwks = await get_jwks()
        if not jwks or "keys" not in jwks:
            return None
            
        header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks["keys"]:
            if key.get("kid") == header.get("kid"):
                rsa_key = {k: key[k] for k in ("kty", "kid", "use", "n", "e") if k in key}
                break
        
        if not rsa_key and jwks["keys"]:
            rsa_key = jwks["keys"][0]
            
        if not rsa_key:
            return None

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(rsa_key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        if "user_id" not in payload and "sub" in payload:
            payload["user_id"] = payload["sub"]
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DEPENDENCY HELPERS
# ---------------------------------------------------------------------------

async def get_current_user(claims: dict = Depends(verify_token)) -> dict:
    """
    Primary dependency — returns the full JWT claims for the authenticated user.
    fetches user's info like id, email, username, etc. from the JWT claims. Raises 401 if token is invalid.
    """
    return claims


# Alias used by all existing endpoints that import `get_current_user_claims`
get_current_user_claims = get_current_user

async def get_user_id(claims: dict = Depends(verify_token)) -> str:
    """Extract the authenticated user's UUID."""
    uid = claims.get("user_id") or claims.get("sub")
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user identity in token.")
    return str(uid)