"""应用 / 配置 / API Key 数据访问。"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app import ApiKey, App, AppConfig


class AppRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, user_id: uuid.UUID, name: str, description: str | None, mode: str
    ) -> App:
        app = App(user_id=user_id, name=name, description=description, mode=mode)
        self.session.add(app)
        await self.session.flush()
        await self.session.refresh(app)
        return app

    async def get(self, app_id: uuid.UUID, user_id: uuid.UUID) -> App | None:
        result = await self.session.execute(
            select(App).where(
                App.id == app_id,
                App.user_id == user_id,
                App.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_any(self, app_id: uuid.UUID) -> App | None:
        """不限用户取应用(供 API Key 对外调用路径使用)。"""
        result = await self.session.execute(
            select(App).where(App.id == app_id, App.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[App]:
        result = await self.session.execute(
            select(App)
            .where(App.user_id == user_id, App.deleted_at.is_(None))
            .order_by(App.updated_at.desc())
        )
        return list(result.scalars().all())

    async def soft_delete(self, app: App) -> None:
        app.deleted_at = func.now()
        await self.session.flush()


class AppConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_version(self, app_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(AppConfig.version), 0)).where(
                AppConfig.app_id == app_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create(
        self,
        *,
        app_id: uuid.UUID,
        version: int,
        model: str | None,
        system_prompt: str | None,
        temperature: float | None,
        max_tokens: int,
        dataset_id: uuid.UUID | None,
    ) -> AppConfig:
        cfg = AppConfig(
            app_id=app_id,
            version=version,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            dataset_id=dataset_id,
        )
        self.session.add(cfg)
        await self.session.flush()
        await self.session.refresh(cfg)
        return cfg

    async def get(self, config_id: uuid.UUID) -> AppConfig | None:
        result = await self.session.execute(
            select(AppConfig).where(AppConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def get_latest(self, app_id: uuid.UUID) -> AppConfig | None:
        result = await self.session.execute(
            select(AppConfig)
            .where(AppConfig.app_id == app_id)
            .order_by(AppConfig.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        app_id: uuid.UUID,
        name: str,
        key_prefix: str,
        key_hash: str,
    ) -> ApiKey:
        key = ApiKey(
            user_id=user_id,
            app_id=app_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
        )
        self.session.add(key)
        await self.session.flush()
        await self.session.refresh(key)
        return key

    async def list_for_app(self, app_id: uuid.UUID) -> list[ApiKey]:
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.app_id == app_id, ApiKey.deleted_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, key_id: uuid.UUID, app_id: uuid.UUID) -> ApiKey | None:
        result = await self.session.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.app_id == app_id,
                ApiKey.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def soft_delete(self, key: ApiKey) -> None:
        key.deleted_at = func.now()
        await self.session.flush()

    async def touch_last_used(self, key_id: uuid.UUID) -> None:
        await self.session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=func.now())
        )
