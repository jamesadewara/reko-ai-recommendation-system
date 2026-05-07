from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.auth import verify_token_http

security = HTTPBearer()

async def get_current_user_http(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Dependency for HTTP routes that extracts and verifies the JWT.
    """
    token = credentials.credentials
    try:
        return verify_token_http(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
