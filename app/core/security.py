import logging
import os
from typing import Optional, Any
from functools import lru_cache

import httpx
import jwt
from fastapi import Request, HTTPException, Security, status, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import PyJWTError, ExpiredSignatureError

from app.core.config import settings

logger = logging.getLogger(__name__)


security = HTTPBearer()

# ── JWKS Cache ──────────────────────────────────────────────────────────────
_JWKS_CACHE: Optional[dict] = None

async def get_jwks() -> dict:
    """
    Fetch and cache the JWKS from the auth service asynchronously.
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


# ── Local RSA Key (RS2A) Loader ──────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_local_public_key() -> Optional[str]:
    """
    Loads the RS256 public key from environment variable or disk.
    This corresponds to the 'RS2A key' mentioned in requirements.
    """
    # 1. Try from environment variable directly
    if settings.JWT_PUBLIC_KEY:
        logger.info("[Security] Using RSA Public Key from environment.")
        return settings.JWT_PUBLIC_KEY

    # 2. Try from local file
    try:
        if os.path.exists(settings.JWT_PUBLIC_KEY_PATH):
            with open(settings.JWT_PUBLIC_KEY_PATH, "r") as f:
                content = f.read().strip()
                if content:
                    logger.info(f"[Security] Using RSA Public Key from {settings.JWT_PUBLIC_KEY_PATH}")
                    return content
    except Exception as e:
        logger.warning(f"[Security] Could not read public key file: {e}")

    return None


async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Verifies an RS256 JWT using either a local RSA public key (RS2A) or remote JWKS.
    Prioritises the local key for performance and reliability.
    """
    token = credentials.credentials
    
    # 1. Attempt Verification with Local RSA Key (RS2A)
    local_key = get_local_public_key()
    if local_key:
        try:
            payload = jwt.decode(
                token,
                local_key,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_aud": False},
            )
            # Normalise user identity
            if "user_id" not in payload and "sub" in payload:
                payload["user_id"] = payload["sub"]

            # Proactively sync/create user in MongoDB
            from app.documents.user import UserDocument
            try:
                await UserDocument.get_or_create_from_token(payload)
            except Exception as e:
                logger.warning(f"[Security] Failed to sync user from token: {e}")

            return payload
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired.")
        except PyJWTError:
            # If local key fails but we have JWKS, we might want to try JWKS 
            # in case keys were rotated and local file is stale.
            if not settings.JWKS_URL:
                raise HTTPException(status_code=401, detail="Invalid token.")
            logger.debug("[Security] Local RSA verification failed, falling back to JWKS")

    # 2. Fallback to JWKS Verification
    jwks = await get_jwks()
    if not jwks or "keys" not in jwks:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service unreachable and no local key available.",
        )

    try:
        header = jwt.get_unverified_header(token)
        rsa_key = {}

        for key in jwks["keys"]:
            if key.get("kid") == header.get("kid"):
                rsa_key = {k: key[k] for k in ("kty", "kid", "use", "n", "e") if k in key}
                break

        if not rsa_key and jwks["keys"]:
            rsa_key = jwks["keys"][0]

        if not rsa_key:
            raise HTTPException(status_code=401, detail="No matching signing key found.")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(rsa_key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )

        if "user_id" not in payload and "sub" in payload:
            payload["user_id"] = payload["sub"]

        # Proactively sync/create user in MongoDB
        from app.documents.user import UserDocument
        try:
            await UserDocument.get_or_create_from_token(payload)
        except Exception as e:
            logger.warning(f"[Security] Failed to sync user from token (JWKS path): {e}")

        return payload

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token invalid: {str(exc)}")


async def verify_internal_service(
    x_internal_secret: str = Header(..., alias="X-Internal-Secret")
) -> bool:
    """
    Dependency to verify requests between internal microservices.
    Requires the X-Internal-Secret header to match settings.
    """
    if not settings.INTERNAL_SERVICE_SECRET:
        logger.error("[Security] INTERNAL_SERVICE_SECRET is not configured!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service misconfiguration: Internal secret not set."
        )

    if x_internal_secret != settings.INTERNAL_SERVICE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal service secret."
        )
    return True


async def get_token_payload_optional(request: Request) -> Optional[dict]:
    """
    Optional Auth: returns JWT claims if token is present and valid, otherwise None.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    try:
        from fastapi.security.utils import get_authorization_scheme_param
        scheme, token = get_authorization_scheme_param(auth_header)
        if scheme.lower() != "bearer":
            return None
            
        # Wrap for verify_token
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        return await verify_token(creds)
    except Exception:
        return None


# ── Dependency Helpers ───────────────────────────────────────────────────────

async def get_current_user_claims(claims: dict = Depends(verify_token)) -> dict:
    """Primary dependency — returns the full JWT claims."""
    return claims

async def get_user_id_from_anywhere(
    request: Request,
    token: Optional[str] = None
) -> str:
    """
    Hybrid dependency that extracts user_id from Authorization header OR 'token' query param.
    Useful for SSE (EventSource) and WebSockets where headers are limited.
    """
    # 1. Try Header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        from fastapi.security.utils import get_authorization_scheme_param
        scheme, creds_token = get_authorization_scheme_param(auth_header)
        if scheme.lower() == "bearer":
            token = creds_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required via header or query param."
        )

    # Wrap for verify_token
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    payload = await verify_token(creds)
    
    uid = payload.get("user_id") or payload.get("sub")
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user identity in token.")
    return str(uid)

async def get_user_id(claims: dict = Depends(verify_token)) -> str:
    """Extract the authenticated user's UUID."""
    uid = claims.get("user_id") or claims.get("sub")
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user identity in token.")
    return str(uid)