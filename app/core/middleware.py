import time
import uuid
from typing import Dict, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.config import settings

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Simple in-memory dict: {ip: (count, first_request_time)}
        self.limits: Dict[str, Tuple[int, float]] = {}
        self.WINDOW_SECONDS = 60
        self.AUTH_LIMIT = 30
        self.GENERAL_LIMIT = 100

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for WebSockets as BaseHTTPMiddleware doesn't support them well
        if request.scope["type"] == "websocket":
            return await call_next(request)

        # Only enforce rate limits in production
        if settings.DEBUG:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Determine limit based on path
        limit = self.AUTH_LIMIT if "/api/v1/auth" in request.url.path else self.GENERAL_LIMIT
        
        if client_ip in self.limits:
            count, first_req = self.limits[client_ip]
            if now - first_req > self.WINDOW_SECONDS:
                # Reset window
                self.limits[client_ip] = (1, now)
            else:
                if count >= limit:
                    retry_after = int(self.WINDOW_SECONDS - (now - first_req))
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too Many Requests"},
                        headers={"Retry-After": str(retry_after)}
                    )
                self.limits[client_ip] = (count + 1, first_req)
        else:
            self.limits[client_ip] = (1, now)
            
        return await call_next(request)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip for WebSockets
        if request.scope["type"] == "websocket":
            return await call_next(request)
            
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        # In a real app, you would inject this into a contextvar for loguru to pick up
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
