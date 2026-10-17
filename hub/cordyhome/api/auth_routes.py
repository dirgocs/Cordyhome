from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..auth import SESSION_COOKIE, SESSION_TTL
from .deps import Services, services

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupBody(Credentials):
    password: str = Field(min_length=8, max_length=256)


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/status")
def auth_status(request: Request, svc: Services = Depends(services)):
    user = svc.auth.user_for_token(request.cookies.get(SESSION_COOKIE))
    return {"setup_required": not svc.auth.has_users(), "user": user}


@router.post("/setup")
def setup(body: SetupBody, request: Request, response: Response, svc: Services = Depends(services)):
    if svc.auth.has_users():
        raise HTTPException(status.HTTP_409_CONFLICT, "A conta de administrador já existe.")
    user_id = svc.auth.create_user(body.username, body.password)
    _set_cookie(request, response, svc.auth.create_session(user_id))
    return {"user": {"id": user_id, "username": body.username.strip()}}


@router.post("/login")
def login(
    body: Credentials, request: Request, response: Response, svc: Services = Depends(services)
):
    key = request.client.host if request.client else "unknown"
    if svc.auth.is_rate_limited(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde alguns minutos."
        )
    user_id = svc.auth.authenticate(body.username, body.password)
    if user_id is None:
        svc.auth.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário ou senha incorretos.")
    svc.auth.clear_failures(key)
    _set_cookie(request, response, svc.auth.create_session(user_id))
    return {"user": {"id": user_id, "username": body.username.strip()}}


@router.post("/logout")
def logout(request: Request, response: Response, svc: Services = Depends(services)):
    svc.auth.revoke(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
