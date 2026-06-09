"""
Pool password gate – authentication router.

Routes
------
POST /auth/verify   – Verify the shared pool password and set a session cookie.
POST /auth/logout   – Clear the pool_authenticated cookie.

Environment
-----------
POOL_PASSWORD   The secret string users must enter to access the pool.
                Set this in your Vercel project settings (or .env locally).
"""

import os
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "pool_authenticated"
COOKIE_MAX_AGE = 2_592_000  # 30 days in seconds


class PasswordPayload(BaseModel):
    password: str


@router.post("/verify")
async def verify_password(payload: PasswordPayload):
    """
    Accepts { "password": "<guess>" } and compares against POOL_PASSWORD.
    On success sets a 30-day httpOnly cookie and returns 200.
    On failure returns 401.
    """
    pool_password = os.environ.get("POOL_PASSWORD", "")

    if not pool_password:
        # Fail closed: if the env var is not set, deny all access.
        return JSONResponse(
            status_code=500,
            content={"detail": "POOL_PASSWORD environment variable is not configured."},
        )

    if payload.password != pool_password:
        return JSONResponse(
            status_code=401,
            content={"detail": "Incorrect password."},
        )

    response = JSONResponse(status_code=200, content={"ok": True})
    response.set_cookie(
        key=COOKIE_NAME,
        value="true",
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,       # HTTPS only (Vercel always serves HTTPS)
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout():
    """Clear the pool authentication cookie."""
    response = JSONResponse(status_code=200, content={"ok": True})
    response.delete_cookie(key=COOKIE_NAME)
    return response
