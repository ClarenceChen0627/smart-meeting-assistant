from __future__ import annotations

from hmac import compare_digest

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse


AUTHORIZATION_HEADER = "Authorization"
API_TOKEN_HEADER = "X-API-Token"
WEBSOCKET_TOKEN_QUERY_PARAM = "access_token"

PUBLIC_HTTP_PATHS = {
    "/",
    "/api/health",
    "/favicon.ico",
}


def _configured_token(request_or_websocket: Request | WebSocket) -> str:
    settings = getattr(request_or_websocket.app.state, "settings", None)
    if settings is None:
        return ""
    return getattr(settings, "api_access_token", "") or ""


def _extract_http_token(request: Request) -> str:
    authorization = request.headers.get(AUTHORIZATION_HEADER, "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get(API_TOKEN_HEADER, "").strip()


def _matches_configured_token(candidate: str, configured: str) -> bool:
    return bool(candidate) and compare_digest(candidate, configured)


def is_http_request_authorized(request: Request) -> bool:
    configured = _configured_token(request)
    if not configured:
        return True
    if request.url.path in PUBLIC_HTTP_PATHS:
        return True
    return _matches_configured_token(_extract_http_token(request), configured)


def is_websocket_authorized(websocket: WebSocket) -> bool:
    configured = _configured_token(websocket)
    if not configured:
        return True
    return _matches_configured_token(
        websocket.query_params.get(WEBSOCKET_TOKEN_QUERY_PARAM, "").strip(),
        configured,
    )


async def api_token_auth_middleware(request: Request, call_next):
    if not is_http_request_authorized(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "API access token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), geolocation=(), payment=(), usb=()",
    )
    return response
