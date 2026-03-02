from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from ..config import settings


async def require_auth(request: Request) -> None:
    """FastAPI dependency that enforces Bearer token authentication.

    If ``celeryhub_auth_token`` is empty the check is skipped (dev mode).
    """
    token = settings.celeryhub_auth_token
    if not token:
        return

    auth_header: str | None = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    if auth_header[7:] != token:
        raise HTTPException(status_code=401, detail="Invalid auth token")
