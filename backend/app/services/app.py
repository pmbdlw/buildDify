"""应用构建器业务逻辑:应用 CRUD、配置版本化与发布、API Key 管理与校验。

配置版本化:每次保存配置自增 version 生成一条新快照;调试用最新版,
对外(API Key)用 app.published_config_id 指向的已发布版。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key
from app.models.app import APP_MODE_CHATBOT, APP_PUBLISHED, ApiKey, App, AppConfig
from app.repositories.app import ApiKeyRepository, AppConfigRepository, AppRepository


class AppError(Exception):
    """应用相关业务错误(未找到 / 状态非法)。"""


class AppService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.apps = AppRepository(session)
        self.configs = AppConfigRepository(session)

    # ---- 应用 ----
    async def create_app(
        self, *, user_id: uuid.UUID, name: str, description: str | None, mode: str
    ) -> App:
        app = await self.apps.create(
            user_id=user_id, name=name, description=description, mode=mode or APP_MODE_CHATBOT
        )
        # 建应用即生成首个空白配置版本(v1),方便随即调试
        await self.configs.create(
            app_id=app.id,
            version=1,
            model=None,
            system_prompt=None,
            temperature=None,
            max_tokens=1024,
            dataset_id=None,
        )
        await self.session.commit()
        await self.session.refresh(app)
        return app

    async def list_apps(self, user_id: uuid.UUID) -> list[App]:
        return await self.apps.list_for_user(user_id)

    async def get_app(self, app_id: uuid.UUID, user_id: uuid.UUID) -> App:
        app = await self.apps.get(app_id, user_id)
        if app is None:
            raise AppError("应用不存在")
        return app

    async def update_app(
        self, *, app_id: uuid.UUID, user_id: uuid.UUID, name: str | None, description: str | None
    ) -> App:
        app = await self.get_app(app_id, user_id)
        if name is not None:
            app.name = name
        if description is not None:
            app.description = description
        await self.session.commit()
        await self.session.refresh(app)
        return app

    async def delete_app(self, *, app_id: uuid.UUID, user_id: uuid.UUID) -> None:
        app = await self.get_app(app_id, user_id)
        await self.apps.soft_delete(app)
        await self.session.commit()

    # ---- 配置(版本化) ----
    async def get_latest_config(self, app_id: uuid.UUID, user_id: uuid.UUID) -> AppConfig:
        await self.get_app(app_id, user_id)  # 鉴权 + 存在性
        cfg = await self.configs.get_latest(app_id)
        if cfg is None:
            raise AppError("配置不存在")
        return cfg

    async def save_config(
        self,
        *,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        model: str | None,
        system_prompt: str | None,
        temperature: float | None,
        max_tokens: int,
        dataset_id: uuid.UUID | None,
    ) -> AppConfig:
        """保存为新版本(自增 version)。"""
        await self.get_app(app_id, user_id)
        version = await self.configs.next_version(app_id)
        cfg = await self.configs.create(
            app_id=app_id,
            version=version,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            dataset_id=dataset_id,
        )
        await self.session.commit()
        await self.session.refresh(cfg)
        return cfg

    async def publish(self, *, app_id: uuid.UUID, user_id: uuid.UUID) -> App:
        """把最新配置版本设为已发布,供 API Key 对外调用。"""
        app = await self.get_app(app_id, user_id)
        latest = await self.configs.get_latest(app_id)
        if latest is None:
            raise AppError("无可发布的配置")
        app.published_config_id = latest.id
        app.status = APP_PUBLISHED
        await self.session.commit()
        await self.session.refresh(app)
        return app

    # ---- 运行态配置解析 ----
    async def get_debug_config(self, app_id: uuid.UUID, user_id: uuid.UUID) -> AppConfig:
        """调试运行用最新配置版本。"""
        return await self.get_latest_config(app_id, user_id)


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.keys = ApiKeyRepository(session)
        self.apps = AppRepository(session)
        self.configs = AppConfigRepository(session)

    async def create_key(
        self, *, app_id: uuid.UUID, user_id: uuid.UUID, name: str
    ) -> tuple[ApiKey, str]:
        """生成 API Key,返回 (记录, 明文)。明文仅此一次可见。"""
        app = await self.apps.get(app_id, user_id)
        if app is None:
            raise AppError("应用不存在")
        raw, prefix, key_hash = generate_api_key()
        key = await self.keys.create(
            user_id=user_id, app_id=app_id, name=name, key_prefix=prefix, key_hash=key_hash
        )
        await self.session.commit()
        await self.session.refresh(key)
        return key, raw

    async def list_keys(self, *, app_id: uuid.UUID, user_id: uuid.UUID) -> list[ApiKey]:
        app = await self.apps.get(app_id, user_id)
        if app is None:
            raise AppError("应用不存在")
        return await self.keys.list_for_app(app_id)

    async def revoke_key(
        self, *, app_id: uuid.UUID, key_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        app = await self.apps.get(app_id, user_id)
        if app is None:
            raise AppError("应用不存在")
        key = await self.keys.get(key_id, app_id)
        if key is None:
            raise AppError("密钥不存在")
        await self.keys.soft_delete(key)
        await self.session.commit()

    async def authenticate(self, raw: str) -> tuple[ApiKey, App, AppConfig]:
        """校验 API Key 明文,返回 (key, 已发布应用, 已发布配置)。"""
        key = await self.keys.get_by_hash(hash_api_key(raw))
        if key is None:
            raise AppError("无效的 API Key")
        app = await self.apps.get_any(key.app_id)
        if app is None or app.published_config_id is None:
            raise AppError("应用未发布")
        config = await self.configs.get(app.published_config_id)
        if config is None:
            raise AppError("应用未发布")
        await self.keys.touch_last_used(key.id)
        await self.session.commit()
        return key, app, config
