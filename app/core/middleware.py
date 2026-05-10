import time
import uuid
from typing import Dict, Tuple
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse
from app.core.config import settings


class RateLimitMiddleware:
    """
    Pure ASGI rate-limit middleware.
    Uses pure ASGI instead of BaseHTTPMiddleware to avoid Starlette's
    'No response returned' RuntimeError that occurs with streaming/async routes.
    """
    def __init__(self, app: ASGIApp):
        self.app = app
        self.limits: Dict[str, Tuple[int, float]] = {}
        self.WINDOW_SECONDS = 60
        self.AUTH_LIMIT = 30
        self.GENERAL_LIMIT = 100

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # Pass through non-HTTP scopes (websocket, lifespan) directly
        if scope["type"] not in ("http",):
            await self.app(scope, receive, send)
            return

        # Skip rate limiting in debug mode
        if settings.DEBUG:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        path = scope.get("path", "")
        now = time.time()

        limit = self.AUTH_LIMIT if "/api/v1/auth" in path else self.GENERAL_LIMIT

        if client_ip in self.limits:
            count, first_req = self.limits[client_ip]
            if now - first_req > self.WINDOW_SECONDS:
                self.limits[client_ip] = (1, now)
            elif count >= limit:
                retry_after = int(self.WINDOW_SECONDS - (now - first_req))
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests"},
                    headers={"Retry-After": str(retry_after)}
                )
                await response(scope, receive, send)
                return
            else:
                self.limits[client_ip] = (count + 1, first_req)
        else:
            self.limits[client_ip] = (1, now)

        await self.app(scope, receive, send)


class RequestIDMiddleware:
    """
    Pure ASGI request-ID middleware.
    Injects an X-Request-ID header into every HTTP response.
    """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode() or str(uuid.uuid4())

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
