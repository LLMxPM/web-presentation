"""文件功能：管理与聊天模型隔离的图片供应商、模型和生成槽位。"""

from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_image_model import AiImageModelConfig, AiImageProviderConfig, AiImageSlotBinding
from app.models.enums import AiLlmConfigScope, AiLlmSlot, RecordStatus, UserRole
from app.schemas.model_config import (
    ImageBindingItem,
    ImageBindingUpdate,
    ImageModelConfigCreate,
    ImageModelConfigItem,
    ImageModelConfigUpdate,
    ImageProviderCatalogItem,
    ImageProviderConfigCreate,
    ImageProviderConfigItem,
    ImageProviderConfigUpdate,
)
from app.services.image_generation.contracts import validate_advanced_options
from app.services.image_generation.registry import (
    get_image_model_spec,
    get_image_provider_spec,
    list_image_provider_specs,
    validate_image_provider_connection,
)


class AiImageConfigService:
    """图片配置领域服务，凭证和模型不与 Chat 共享。"""

    def __init__(self, session: AsyncSession, *, user_id: int, user_role: str) -> None:
        self.session = session
        self.user_id = user_id
        self.user_role = user_role
        self.cipher = LlmSecretCipher()

    def list_catalog(self) -> list[ImageProviderCatalogItem]:
        """返回代码注册表中的图片供应商能力。"""

        return [ImageProviderCatalogItem(provider_key=item.provider_key, name=item.label, docs_url=item.docs_url,
            default_base_url=item.default_base_url, requires_base_url=item.requires_base_url,
            models=[model.as_catalog_item() for model in item.models]) for item in list_image_provider_specs()]

    async def list_providers(self) -> list[ImageProviderConfigItem]:
        """列出可见图片供应商连接。"""

        rows = (await self.session.scalars(self._visible(AiImageProviderConfig).order_by(AiImageProviderConfig.updated_at.desc()))).all()
        return [self._provider_item(row) for row in rows]

    async def create_provider(self, payload: ImageProviderConfigCreate, *, operator_id: int) -> ImageProviderConfigItem:
        """创建图片供应商连接并执行注册表约束。"""

        self._require_scope(payload.scope)
        spec = get_image_provider_spec(payload.provider_key)
        base_url = self._text(payload.base_url) or spec.default_base_url
        if spec.requires_base_url and not base_url:
            raise AppException(status_code=400, code="AI_IMAGE_BASE_URL_REQUIRED", detail="当前图片供应商必须填写 Base URL。")
        validate_image_provider_connection(spec.provider_key, base_url)
        row = AiImageProviderConfig(user_id=None if payload.scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=payload.scope.value, name=payload.name.strip(), provider_key=spec.provider_key, base_url=base_url,
            api_key_ciphertext=self.cipher.encrypt(self._text(payload.api_key)), status=RecordStatus.ACTIVE.value,
            created_by=operator_id, updated_by=operator_id)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._provider_item(row)

    async def update_provider(self, row_id: int, payload: ImageProviderConfigUpdate, *, operator_id: int) -> ImageProviderConfigItem:
        """更新图片连接但不允许切换供应商。"""

        row = await self._provider(row_id, editable=True)
        spec = get_image_provider_spec(row.provider_key)
        if payload.name is not None:
            row.name = payload.name.strip()
        if "base_url" in payload.model_fields_set:
            row.base_url = self._text(payload.base_url)
        if spec.requires_base_url and not row.base_url:
            raise AppException(status_code=400, code="AI_IMAGE_BASE_URL_REQUIRED", detail="当前图片供应商必须填写 Base URL。")
        validate_image_provider_connection(row.provider_key, row.base_url)
        if "api_key" in payload.model_fields_set:
            row.api_key_ciphertext = self.cipher.encrypt(self._text(payload.api_key))
        if payload.status is not None:
            row.status = payload.status
        row.updated_by = operator_id
        await self.session.commit()
        return self._provider_item(row)

    async def delete_provider(self, row_id: int) -> None:
        """删除没有图片模型引用的连接。"""

        row = await self._provider(row_id, editable=True)
        if await self.session.scalar(select(AiImageModelConfig.id).where(AiImageModelConfig.provider_config_id == row.id).limit(1)):
            raise AppException(status_code=409, code="AI_IMAGE_PROVIDER_IN_USE", detail="请先删除该供应商下的图片模型。")
        await self.session.delete(row)
        await self.session.commit()

    async def list_models(self) -> list[ImageModelConfigItem]:
        """列出可见图片模型。"""

        rows = (await self.session.scalars(self._visible(AiImageModelConfig).options(
            selectinload(AiImageModelConfig.provider_config)).order_by(AiImageModelConfig.updated_at.desc()))).all()
        return [self._model_item(row) for row in rows]

    async def create_model(self, payload: ImageModelConfigCreate, *, operator_id: int) -> ImageModelConfigItem:
        """创建图片模型并按注册表校验高级参数。"""

        self._require_scope(payload.scope)
        provider = await self._provider(payload.provider_config_id, selectable=True)
        self._same_scope(payload.scope.value, provider.scope)
        spec = get_image_model_spec(provider.provider_key, payload.model_id)
        advanced = validate_advanced_options(spec, payload.advanced_config)
        row = AiImageModelConfig(user_id=None if payload.scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=payload.scope.value, name=payload.name.strip(), provider_config_id=provider.id,
            model_id=payload.model_id.strip(), advanced_config_json=advanced, status=RecordStatus.ACTIVE.value,
            created_by=operator_id, updated_by=operator_id)
        row.provider_config = provider
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        row.provider_config = provider
        return self._model_item(row)

    async def update_model(self, row_id: int, payload: ImageModelConfigUpdate, *, operator_id: int) -> ImageModelConfigItem:
        """更新图片模型并重新校验能力参数。"""

        row = await self._model(row_id, editable=True)
        provider = await self._provider(payload.provider_config_id, selectable=True) if payload.provider_config_id else row.provider_config
        self._same_scope(row.scope, provider.scope)
        model_id = payload.model_id.strip() if payload.model_id else row.model_id
        spec = get_image_model_spec(provider.provider_key, model_id)
        advanced = validate_advanced_options(spec, payload.advanced_config if payload.advanced_config is not None else row.advanced_config_json)
        if payload.name is not None:
            row.name = payload.name.strip()
        row.provider_config_id = provider.id
        row.provider_config = provider
        row.model_id = model_id
        row.advanced_config_json = advanced
        if payload.status is not None:
            row.status = payload.status
        row.updated_by = operator_id
        await self.session.commit()
        return self._model_item(row)

    async def delete_model(self, row_id: int) -> None:
        """无任务引用时删除图片模型和绑定。"""

        row = await self._model(row_id, editable=True)
        if await self.session.scalar(select(AiImageGenerationJob.id).where(AiImageGenerationJob.model_config_id == row.id).limit(1)):
            raise AppException(status_code=409, code="AI_IMAGE_MODEL_JOB_IN_USE", detail="当前图片模型已有任务记录，不能删除。")
        await self.session.execute(delete(AiImageSlotBinding).where(AiImageSlotBinding.model_config_id == row.id))
        await self.session.delete(row)
        await self.session.commit()

    async def get_binding(self) -> ImageBindingItem:
        """读取个人图片生成绑定并回落全局。"""

        personal = await self._binding(AiLlmConfigScope.PERSONAL.value, self.user_id)
        binding = personal or await self._binding(AiLlmConfigScope.GLOBAL.value, None)
        return self._binding_item(binding, inherited=personal is None and binding is not None)

    async def update_binding(self, payload: ImageBindingUpdate, *, operator_id: int) -> ImageBindingItem:
        """更新唯一的图片生成槽位。"""

        self._require_scope(payload.scope)
        user_id = None if payload.scope == AiLlmConfigScope.GLOBAL else self.user_id
        binding = await self._binding(payload.scope.value, user_id)
        if payload.model_config_id is None:
            if binding:
                await self.session.delete(binding)
                await self.session.commit()
            return ImageBindingItem(binding_ready=False)
        model = await self._model(payload.model_config_id, selectable=True)
        self._same_scope(payload.scope.value, model.scope)
        if binding is None:
            binding = AiImageSlotBinding(user_id=user_id, scope=payload.scope.value, slot=AiLlmSlot.IMAGE_GENERATION.value,
                created_by=operator_id)
            self.session.add(binding)
        binding.model_config_id = model.id
        binding.model_config = model
        binding.updated_by = operator_id
        await self.session.commit()
        return self._binding_item(binding, inherited=False)

    async def get_bound_model_or_raise(self) -> AiImageModelConfig:
        """供图片任务链路读取生效模型。"""

        personal = await self._binding(AiLlmConfigScope.PERSONAL.value, self.user_id)
        binding = personal or await self._binding(AiLlmConfigScope.GLOBAL.value, None)
        if binding is None or binding.model_config is None or binding.model_config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_IMAGE_SLOT_UNBOUND", detail="图片生成槽位未绑定可用模型。")
        return binding.model_config

    def _provider_item(self, row: AiImageProviderConfig) -> ImageProviderConfigItem:
        spec = get_image_provider_spec(row.provider_key)
        secret = self.cipher.decrypt(row.api_key_ciphertext)
        return ImageProviderConfigItem(id=row.id, scope=row.scope, editable=self._editable(row.scope, row.user_id), name=row.name,
            provider_key=row.provider_key, provider_name=spec.label, base_url=row.base_url, has_api_key=bool(secret),
            api_key_masked=self.cipher.mask(secret) if secret else None, status=row.status)

    def _model_item(self, row: AiImageModelConfig) -> ImageModelConfigItem:
        spec = get_image_model_spec(row.provider_config.provider_key, row.model_id)
        return ImageModelConfigItem(id=row.id, scope=row.scope, editable=self._editable(row.scope, row.user_id), name=row.name,
            provider_config_id=row.provider_config_id, provider_name=row.provider_config.name, provider_key=row.provider_config.provider_key,
            model_id=row.model_id, capability=spec.as_catalog_item(), advanced_config=dict(row.advanced_config_json or {}), status=row.status)

    def _binding_item(self, binding: AiImageSlotBinding | None, *, inherited: bool) -> ImageBindingItem:
        if binding is None or binding.model_config is None:
            return ImageBindingItem(binding_ready=False)
        model = binding.model_config
        provider = model.provider_config
        spec = get_image_provider_spec(provider.provider_key)
        return ImageBindingItem(model_config_id=model.id, model_name=model.name,
            provider_config_id=provider.id, provider_config_name=provider.name, provider_key=provider.provider_key,
            provider_name=spec.label, model_id=model.model_id,
            binding_ready=model.status == RecordStatus.ACTIVE.value and model.provider_config.status == RecordStatus.ACTIVE.value,
            inherited_from_global=inherited)

    def _visible(self, model):  # noqa: ANN001
        return select(model).where(or_(model.scope == AiLlmConfigScope.GLOBAL.value,
            (model.scope == AiLlmConfigScope.PERSONAL.value) & (model.user_id == self.user_id)))

    async def _provider(self, row_id: int, *, editable: bool = False, selectable: bool = False) -> AiImageProviderConfig:
        row = await self.session.get(AiImageProviderConfig, row_id)
        if row is None or not self._readable(row.scope, row.user_id):
            raise AppException(status_code=404, code="AI_IMAGE_PROVIDER_NOT_FOUND", detail="图片供应商不存在。")
        if editable and not self._editable(row.scope, row.user_id):
            raise AppException(status_code=403, code="AI_IMAGE_PROVIDER_READONLY", detail="当前图片供应商不可编辑。")
        if selectable and row.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_IMAGE_PROVIDER_DISABLED", detail="图片供应商未启用。")
        return row

    async def _model(self, row_id: int, *, editable: bool = False, selectable: bool = False) -> AiImageModelConfig:
        row = await self.session.scalar(select(AiImageModelConfig).where(AiImageModelConfig.id == row_id).options(selectinload(AiImageModelConfig.provider_config)))
        if row is None or not self._readable(row.scope, row.user_id):
            raise AppException(status_code=404, code="AI_IMAGE_MODEL_NOT_FOUND", detail="图片模型不存在。")
        if editable and not self._editable(row.scope, row.user_id):
            raise AppException(status_code=403, code="AI_IMAGE_MODEL_READONLY", detail="当前图片模型不可编辑。")
        if selectable and (row.status != RecordStatus.ACTIVE.value or row.provider_config.status != RecordStatus.ACTIVE.value):
            raise AppException(status_code=409, code="AI_IMAGE_MODEL_DISABLED", detail="图片模型或供应商未启用。")
        return row

    async def _binding(self, scope: str, user_id: int | None) -> AiImageSlotBinding | None:
        return await self.session.scalar(select(AiImageSlotBinding).where(AiImageSlotBinding.slot == AiLlmSlot.IMAGE_GENERATION.value,
            AiImageSlotBinding.scope == scope, AiImageSlotBinding.user_id == user_id)
            .options(selectinload(AiImageSlotBinding.model_config).selectinload(AiImageModelConfig.provider_config)))

    def _require_scope(self, scope: AiLlmConfigScope) -> None:
        if scope == AiLlmConfigScope.GLOBAL and self.user_role != UserRole.PLATFORM_ADMIN.value:
            raise AppException(status_code=403, code="AI_IMAGE_GLOBAL_ADMIN_REQUIRED", detail="只有平台管理员可以维护全局图片模型。")

    def _readable(self, scope: str, owner: int | None) -> bool:
        return scope == AiLlmConfigScope.GLOBAL.value or owner == self.user_id

    def _editable(self, scope: str, owner: int | None) -> bool:
        return (scope == AiLlmConfigScope.GLOBAL.value and self.user_role == UserRole.PLATFORM_ADMIN.value) or owner == self.user_id

    @staticmethod
    def _same_scope(expected: str, actual: str) -> None:
        if expected != actual:
            raise AppException(status_code=409, code="AI_IMAGE_SCOPE_MISMATCH", detail="图片供应商、模型和绑定必须属于同一范围。")

    @staticmethod
    def _text(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None
