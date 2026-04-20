"""REST API for proxy access management."""

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

API_KEY = os.environ["API_KEY"]

app = FastAPI(title="MTProxy Access API", version="1.0.0")

# Injected from main.py after manager is initialised
_manager = None


def set_manager(manager):
    global _manager
    _manager = manager


# ── auth ──────────────────────────────────────────────────────────────────────

async def require_api_key(x_api_key: Annotated[str | None, Header()] = None):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


AuthDep = Annotated[None, Depends(require_api_key)]


# ── schemas ───────────────────────────────────────────────────────────────────

class AccessRequest(BaseModel):
    user_id: str


class AccessResponse(BaseModel):
    user_id: str
    link: str
    created: bool  # False = already existed


class LinkResponse(BaseModel):
    user_id: str
    link: str


class UserEntry(BaseModel):
    user_id: str
    link: str


# ── routes ────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/access",
    response_model=AccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant proxy access to a user",
)
async def create_access(_: AuthDep, body: AccessRequest):
    """
    Выдаёт доступ пользователю. Генерирует уникальный secret, обновляет конфиг прокси.
    Если пользователь уже существует — возвращает его текущую ссылку (created=false).
    """
    created, secret = await _manager.allow(body.user_id)
    link = _manager.build_link(secret)
    status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return JSONResponse(
        status_code=status_code,
        content=AccessResponse(user_id=body.user_id, link=link, created=created).model_dump(),
    )


@app.delete(
    "/api/v1/access/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke proxy access",
)
async def delete_access(_: AuthDep, user_id: str):
    """
    Отзывает доступ пользователя. Удаляет его secret и перезапускает прокси.
    """
    found = await _manager.revoke(user_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@app.get(
    "/api/v1/access/{user_id}/link",
    response_model=LinkResponse,
    summary="Get proxy link for a user",
)
async def get_link(_: AuthDep, user_id: str):
    """
    Возвращает персональную ссылку для подключения к прокси.
    """
    link = await _manager.get_link(user_id)
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return LinkResponse(user_id=user_id, link=link)


@app.get(
    "/api/v1/access",
    response_model=list[UserEntry],
    summary="List all users with access",
)
async def list_access(_: AuthDep):
    """
    Список всех пользователей с доступом и их ссылками.
    """
    users = await _manager.list_users()
    return [UserEntry(user_id=uid, link=_manager.build_link(secret)) for uid, secret in users.items()]


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
