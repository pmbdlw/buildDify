"""鉴权业务逻辑:注册、登录。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import LoginIn, RegisterIn


class AuthError(Exception):
    """鉴权失败(邮箱已存在 / 凭证错误)。"""


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, data: RegisterIn) -> User:
        if await self.users.get_by_email(data.email):
            raise AuthError("邮箱已被注册")
        user = await self.users.create(
            email=data.email,
            password_hash=hash_password(data.password),
            name=data.name,
        )
        await self.session.commit()
        return user

    async def login(self, data: LoginIn) -> str:
        user = await self.users.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise AuthError("邮箱或密码错误")
        if not user.is_active:
            raise AuthError("账号已禁用")
        return create_access_token(str(user.id))
