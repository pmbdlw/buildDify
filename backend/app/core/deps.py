"""FastAPI 鉴权依赖。"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user import UserRepository

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的凭证"
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except Exception as exc:  # noqa: BLE001
        raise invalid from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        raise invalid
    return user
