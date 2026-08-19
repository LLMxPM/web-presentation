"""文件功能：同步、过滤并查询 Models.dev 聊天模型目录缓存。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.model_protocols import resolve_catalog_protocol, resolve_model_catalog_protocol
from app.ai.reasoning_controls import normalize_reasoning_options
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_model_catalog import AiChatModelCatalog, AiChatProviderCatalog, AiModelCatalogSyncState

logger = logging.getLogger(__name__)

MODELS_DEV_URL = "https://models.dev/api.json"
MAX_CATALOG_BYTES = 24 * 1024 * 1024
SYNC_INTERVAL = timedelta(hours=24)
LEASE_DURATION = timedelta(minutes=10)


class ModelsDevLimit(BaseModel):
    """Models.dev 模型 token 上限。"""

    model_config = ConfigDict(extra="allow")
    context: int | None = None
    input: int | None = None
    output: int | None = None


class ModelsDevModalities(BaseModel):
    """Models.dev 模型输入输出模态。"""

    model_config = ConfigDict(extra="allow")
    input: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)


class ModelsDevModelProvider(BaseModel):
    """Models.dev 模型级供应商覆盖；当前只消费 SDK 包名。"""

    model_config = ConfigDict(extra="allow")
    npm: str | None = None


class ModelsDevModel(BaseModel):
    """仅约束平台实际消费的模型字段，其余字段保存在原始快照。"""

    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    family: str | None = None
    status: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    limit: ModelsDevLimit = Field(default_factory=ModelsDevLimit)
    modalities: ModelsDevModalities = Field(default_factory=ModelsDevModalities)
    tool_call: bool = False
    structured_output: bool = False
    attachment: bool = False
    reasoning: bool = False
    reasoning_options: Any = Field(default_factory=dict)
    provider: ModelsDevModelProvider | None = None


class ModelsDevProvider(BaseModel):
    """Models.dev 供应商记录。"""

    model_config = ConfigDict(extra="allow")
    id: str | None = None
    name: str
    api: str | None = None
    doc: str | None = None
    env: list[str] = Field(default_factory=list)
    npm: str | None = None
    models: dict[str, ModelsDevModel] = Field(default_factory=dict)


class AiModelCatalogService:
    """提供目录查询、原子同步和多实例租约。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_providers(self, *, query: str | None = None) -> list[AiChatProviderCatalog]:
        """返回当前受支持供应商，目录失效项不再用于新建配置。"""

        statement = select(AiChatProviderCatalog).where(AiChatProviderCatalog.is_current.is_(True))
        normalized = str(query or "").strip()
        if normalized:
            pattern = f"%{normalized}%"
            statement = statement.where(
                or_(AiChatProviderCatalog.name.ilike(pattern), AiChatProviderCatalog.provider_key.ilike(pattern))
            )
        return list((await self.session.scalars(statement.order_by(AiChatProviderCatalog.name.asc()))).all())

    async def list_models(
        self,
        provider_key: str,
        *,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[AiChatModelCatalog]:
        """分页查询单个供应商的当前模型。"""

        statement = select(AiChatModelCatalog).where(
            AiChatModelCatalog.provider_key == provider_key,
            AiChatModelCatalog.is_current.is_(True),
        )
        normalized = str(query or "").strip()
        if normalized:
            pattern = f"%{normalized}%"
            statement = statement.where(
                or_(AiChatModelCatalog.name.ilike(pattern), AiChatModelCatalog.model_id.ilike(pattern))
            )
        statement = statement.order_by(AiChatModelCatalog.name.asc())
        provider = await self.session.get(AiChatProviderCatalog, provider_key)
        if provider is None or not provider.is_current:
            return []
        models = list((await self.session.scalars(statement)).all())
        supported_models: list[AiChatModelCatalog] = []
        for model in models:
            raw_provider = (model.source_json or {}).get("provider")
            model_protocol = resolve_model_catalog_protocol(
                provider_key,
                provider.npm_package,
                raw_provider.get("npm") if isinstance(raw_provider, dict) else None,
            )
            if model_protocol is None:
                continue
            # 旧缓存可能尚未写入模型级协议，读取时仍返回按快照计算的最终值。
            model.protocol_key = model_protocol
            supported_models.append(model)
        start = max(0, offset)
        return supported_models[start : start + min(200, max(1, limit))]

    async def get_state(self) -> AiModelCatalogSyncState:
        """读取同步状态；空库返回尚未同步的临时对象。"""

        state = await self.session.get(AiModelCatalogSyncState, 1)
        return state or AiModelCatalogSyncState(id=1)

    async def ensure_minimal_catalog(self) -> None:
        """空库写入小型启动目录，离线部署也可完成首次配置。"""

        if await self.session.scalar(select(AiChatProviderCatalog.provider_key).limit(1)) is not None:
            return
        raw: dict[str, Any] = {
            "openai": {"id": "openai", "name": "OpenAI", "api": "https://api.openai.com/v1", "doc": "https://developers.openai.com/api/docs", "env": ["OPENAI_API_KEY"], "npm": "@ai-sdk/openai", "models": {
                "gpt-4.1": {"id": "gpt-4.1", "name": "GPT-4.1", "limit": {"context": 1048576, "input": 1015808, "output": 32768}, "modalities": {"input": ["text", "image"], "output": ["text"]}, "tool_call": True, "structured_output": True}
            }},
            "openrouter": {"id": "openrouter", "name": "OpenRouter", "api": "https://openrouter.ai/api/v1", "doc": "https://openrouter.ai/docs", "env": ["OPENROUTER_API_KEY"], "npm": "@openrouter/ai-sdk-provider", "models": {}},
            "google": {"id": "google", "name": "Google", "doc": "https://ai.google.dev/gemini-api/docs", "env": ["GOOGLE_GENERATIVE_AI_API_KEY"], "npm": "@ai-sdk/google", "models": {}},
            "deepseek": {"id": "deepseek", "name": "DeepSeek", "api": "https://api.deepseek.com", "doc": "https://api-docs.deepseek.com", "env": ["DEEPSEEK_API_KEY"], "npm": "@ai-sdk/openai-compatible", "models": {}},
            "alibaba": {"id": "alibaba", "name": "Alibaba Cloud", "api": "https://dashscope.aliyuncs.com/compatible-mode/v1", "doc": "https://help.aliyun.com/model-studio", "env": ["DASHSCOPE_API_KEY"], "npm": "@ai-sdk/openai-compatible", "models": {}},
        }
        providers = {key: ModelsDevProvider.model_validate(value) for key, value in raw.items()}
        await self._apply_catalog(providers, raw, version="bootstrap-v1")
        state = await self.session.get(AiModelCatalogSyncState, 1)
        if state is None:
            state = AiModelCatalogSyncState(id=1)
            self.session.add(state)
        state.catalog_version = state.catalog_version or "bootstrap-v1"
        await self.session.commit()

    async def sync(self, *, force: bool = False, client: httpx.AsyncClient | None = None) -> AiModelCatalogSyncState:
        """抓取并原子写入目录；任何解析或写入失败均保留旧目录。"""

        owner = uuid.uuid4().hex
        state = await self._acquire_lease(owner, force=force)
        if state.lease_owner != owner:
            return state
        headers = {"Accept": "application/json"}
        if state.etag and not force:
            headers["If-None-Match"] = state.etag
        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=True)
        try:
            response = await http.get(MODELS_DEV_URL, headers=headers)
            if response.status_code == 304:
                state.last_attempt_at = utc_now()
                state.last_success_at = utc_now()
                state.last_error = None
                self._release_lease(state)
                await self.session.commit()
                return state
            response.raise_for_status()
            content = response.content
            if len(content) > MAX_CATALOG_BYTES:
                raise ValueError("Models.dev 响应超过平台允许的 24 MiB。")
            raw = json.loads(content)
            if not isinstance(raw, dict):
                raise ValueError("Models.dev 顶层必须是 provider object。")
            providers = {key: ModelsDevProvider.model_validate(value) for key, value in raw.items()}
            version = hashlib.sha256(content).hexdigest()[:16]
            await self._apply_catalog(providers, raw, version=version)
            state.etag = response.headers.get("etag")
            state.catalog_version = version
            state.last_attempt_at = utc_now()
            state.last_success_at = utc_now()
            state.last_error = None
            self._release_lease(state)
            await self.session.commit()
            return state
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, ValueError, SQLAlchemyError) as exc:
            await self.session.rollback()
            state = await self.session.get(AiModelCatalogSyncState, 1) or AiModelCatalogSyncState(id=1)
            state.last_attempt_at = utc_now()
            state.last_error = str(exc)[:2000]
            self._release_lease(state)
            self.session.add(state)
            await self.session.commit()
            raise AppException(status_code=502, code="AI_MODEL_CATALOG_SYNC_FAILED", detail="模型目录同步失败，已继续使用上一版缓存。") from exc
        finally:
            if owns_client:
                await http.aclose()

    async def _acquire_lease(self, owner: str, *, force: bool) -> AiModelCatalogSyncState:
        """锁定单例状态行，避免多个 Backend 同时更新目录。"""

        now = utc_now()
        state = await self.session.get(AiModelCatalogSyncState, 1, with_for_update=True)
        if state is None:
            state = AiModelCatalogSyncState(id=1)
            self.session.add(state)
            await self.session.flush()
        if state.lease_expires_at and state.lease_expires_at > now:
            raise AppException(status_code=409, code="AI_MODEL_CATALOG_SYNC_RUNNING", detail="模型目录正在同步。")
        if not force and state.last_success_at and now - state.last_success_at < SYNC_INTERVAL:
            return state
        state.lease_owner = owner
        state.lease_expires_at = now + LEASE_DURATION
        state.last_attempt_at = now
        await self.session.commit()
        return state

    async def _apply_catalog(
        self,
        providers: dict[str, ModelsDevProvider],
        raw: dict[str, Any],
        *,
        version: str,
    ) -> None:
        """在当前事务中 upsert 受支持记录，并将缺失记录标记为非当前。"""

        now = utc_now()
        existing_providers = {item.provider_key: item for item in (await self.session.scalars(select(AiChatProviderCatalog))).all()}
        existing_models = {
            (item.provider_key, item.model_id): item for item in (await self.session.scalars(select(AiChatModelCatalog))).all()
        }
        current_provider_keys: set[str] = set()
        current_model_keys: set[tuple[str, str]] = set()
        for provider_key, source in providers.items():
            protocol_key = resolve_catalog_protocol(provider_key, source.npm)
            if protocol_key is None:
                continue
            current_provider_keys.add(provider_key)
            provider = existing_providers.get(provider_key) or AiChatProviderCatalog(provider_key=provider_key)
            provider.name = source.name
            provider.api_url = source.api
            provider.docs_url = source.doc
            provider.default_base_url = source.api
            provider.npm_package = source.npm
            provider.env_keys_json = list(source.env)
            provider.protocol_key = protocol_key
            provider.is_current = True
            provider.catalog_version = version
            provider.source_json = dict(raw.get(provider_key) or {})
            provider.synced_at = now
            self.session.add(provider)
            for model_key, source_model in source.models.items():
                model_id = str(source_model.id or model_key).strip()
                model_protocol = resolve_model_catalog_protocol(
                    provider_key,
                    source.npm,
                    source_model.provider.npm if source_model.provider else None,
                )
                if model_protocol is None:
                    # 供应商可能承载多个 SDK 协议；当前平台不支持的模型不能
                    # 仅因供应商本身可用而泄漏到模型选择器。
                    continue
                key = (provider_key, model_id)
                current_model_keys.add(key)
                model = existing_models.get(key) or AiChatModelCatalog(provider_key=provider_key, model_id=model_id)
                model.name = source_model.name or model_id
                model.protocol_key = model_protocol
                model.family = source_model.family
                model.status = source_model.status
                model.release_date = source_model.release_date
                model.last_updated = source_model.last_updated
                model.context_tokens = source_model.limit.context
                model.input_tokens = source_model.limit.input
                model.output_tokens = source_model.limit.output
                model.input_modalities_json = list(source_model.modalities.input)
                model.output_modalities_json = list(source_model.modalities.output)
                model.supports_tool_call = source_model.tool_call
                model.supports_structured_output = source_model.structured_output
                model.supports_attachment = source_model.attachment
                model.supports_reasoning = source_model.reasoning
                model.reasoning_options_json = normalize_reasoning_options(source_model.reasoning_options)
                model.is_current = True
                model.catalog_version = version
                model.source_json = source_model.model_dump(mode="json")
                model.synced_at = now
                self.session.add(model)
        for key, provider in existing_providers.items():
            if key not in current_provider_keys:
                provider.is_current = False
        for key, model in existing_models.items():
            if key not in current_model_keys:
                model.is_current = False
        await self.session.flush()

    @staticmethod
    def _release_lease(state: AiModelCatalogSyncState) -> None:
        """释放同步租约。"""

        state.lease_owner = None
        state.lease_expires_at = None


async def run_model_catalog_sync_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """每天检查目录新版本；失败仅记录日志，不影响已有 AI 能力。"""

    while True:
        try:
            async with session_factory() as session:
                await AiModelCatalogService(session).sync()
        except AppException as exc:
            if exc.code not in {"AI_MODEL_CATALOG_SYNC_RUNNING"}:
                logger.warning("模型目录后台同步未成功：%s", exc.detail)
        except Exception:  # noqa: BLE001
            logger.exception("模型目录后台同步出现未处理异常。")
        await asyncio.sleep(3600)
