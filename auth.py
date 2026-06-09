"""
Admin auth helpers.

Supports two mechanisms (checked in order):
  1. Cookie  `admin_session=<token>`  – set by POST /admin/login, used by all
     browser / HTMX requests automatically.
  2. Header  `Authorization: Bearer <token>`  – for API / curl clients.

A missing or wrong credential raises 403, never 422.
"""

from fastapi import Cookie, Depends, HTTPException, Header, Request
from typing import Optional
from config import get_settings


def _is_valid_token(token: str | None) -> bool:
    if not token:
        return False
    return token == get_settings().admin_token


async def require_admin(
    request: Request,
    admin_session: Optional[str] = Cookie(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """
    FastAPI dependency.  Accepts either:
      • Cookie  admin_session=<raw_token>
      • Header  Authorization: Bearer <token>
    Raises HTTP 403 on failure; never 422.
    """
    # 1. Cookie-based session (browser / HTMX)
    if _is_valid_token(admin_session):
        return

    # 2. Bearer token (API clients / curl)
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and _is_valid_token(token):
            return

    raise HTTPException(status_code=403, detail="Admin access required.")
