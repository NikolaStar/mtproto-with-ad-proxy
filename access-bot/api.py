"""REST API for proxy access management."""

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

API_KEY = os.environ["API_KEY"]

app = FastAPI(
    title="MTProxy Access API",
    version="1.1.0",
    description=(
        "Управление доступами к MTProto прокси. "
        "Поле `user_id` — произвольный строковый идентификатор: "
        "Telegram user_id (`123456789`) или кастомное имя (`vasya`, `client_abc`). "
        "Поле `no_ad=true` выдаёт доступ на инстанс без спонсорской рекламы."
    ),
)

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
    no_ad: bool = False  # True = ad-free proxy instance (PROXY_PORT_NOAD)


class AccessResponse(BaseModel):
    user_id: str
    link: str
    created: bool  # False = already existed
    no_ad: bool


class LinkResponse(BaseModel):
    user_id: str
    link: str
    no_ad: bool


class UserEntry(BaseModel):
    user_id: str
    link: str
    no_ad: bool


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
    `no_ad=true` — добавить на инстанс без рекламы (порт PROXY_PORT_NOAD).
    """
    created, secret = await _manager.allow(body.user_id, no_ad=body.no_ad)
    # Resolve actual tier (user may already exist in the other tier)
    info = await _manager.get_secret(body.user_id)
    actual_secret, actual_no_ad = info
    link = _manager.build_link(actual_secret, actual_no_ad)
    status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return JSONResponse(
        status_code=status_code,
        content=AccessResponse(
            user_id=body.user_id, link=link, created=created, no_ad=actual_no_ad
        ).model_dump(),
    )


class MoveRequest(BaseModel):
    no_ad: bool


@app.patch(
    "/api/v1/access/{user_id}",
    response_model=AccessResponse,
    summary="Move user to a different tier",
)
async def move_access(_: AuthDep, user_id: str, body: MoveRequest):
    """
    Перемещает пользователя на другой инстанс (с рекламой / без).
    Генерирует новый secret. Возвращает moved=false если пользователь уже на нужном инстансе.
    """
    moved, link = await _manager.move(user_id, no_ad=body.no_ad)
    if not moved:
        info = await _manager.get_secret(user_id)
        if not info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AccessResponse(user_id=user_id, link=link, created=moved, no_ad=body.no_ad)


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
    info = await _manager.get_secret(user_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    secret, no_ad = info
    link = _manager.build_link(secret, no_ad)
    return LinkResponse(user_id=user_id, link=link, no_ad=no_ad)


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
    return [
        UserEntry(user_id=uid, link=_manager.build_link(secret, no_ad), no_ad=no_ad)
        for uid, (secret, no_ad) in users.items()
    ]


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
