"""文件功能：管理聊天供应商、模型能力合并和槽位级运行策略。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.provider_catalog import PROTECTED_ADVANCED_CONFIG_KEYS
from app.ai.reasoning_controls import (
    protocol_reasoning_controls,
    reasoning_budget_limits,
    reasoning_control_types,
    reasoning_effort_options,
    supports_explicit_disable,
)
from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_llm import AiChatModelConfig, AiChatProviderConfig, AiChatSlotBinding
from app.models.ai_model_catalog import AiChatModelCatalog, AiChatProviderCatalog
from app.models.enums import AiLlmConfigScope, AiLlmSlot, RecordStatus, UserRole
from app.schemas.model_config import (
    ChatBindingItem,
    ChatBindingUpdate,
    ChatModelConfigCreate,
    ChatModelConfigItem,
    ChatModelConfigUpdate,
    ChatProviderConfigCreate,
    ChatProviderConfigItem,
    ChatProviderConfigUpdate,
    ReasoningPolicy,
)

CUSTOM_PROVIDER_KEY = "custom-openai-compatible"
CUSTOM_PROTOCOL_KEY = "openai_compatible_chat"
DEFAULT_CONTEXT_TOKENS = 200_000
DEFAULT_OUTPUT_TOKENS = 8_192


class AiChatConfigService:
    """聊天配置领域服务，不接受图片模型或运行时 adapter 覆盖。"""

    def __init__(self, session: AsyncSession, *, user_id: int, user_role: str) -> None:
        self.session = session
        self.user_id = user_id
        self.user_role = user_role
        self.cipher = LlmSecretCipher()

    async def list_providers(self) -> list[ChatProviderConfigItem]:
        """列出个人和全局聊天供应商连接。"""

        rows = (await self.session.scalars(self._visible(AiChatProviderConfig).order_by(AiChatProviderConfig.updated_at.desc()))).all()
        return [await self._provider_item(row) for row in rows]

    async def create_provider(self, payload: ChatProviderConfigCreate, *, operator_id: int) -> ChatProviderConfigItem:
        """创建目录连接或固定为 OpenAI-compatible 的自定义连接。"""

        self._require_scope_write(payload.scope)
        catalog: AiChatProviderCatalog | None = None
        if payload.catalog_provider_key:
            catalog = await self.session.get(AiChatProviderCatalog, payload.catalog_provider_key)
            if catalog is None:
                from app.services.ai_model_catalog_service import AiModelCatalogService

                await AiModelCatalogService(self.session).ensure_minimal_catalog()
                catalog = await self.session.get(AiChatProviderCatalog, payload.catalog_provider_key)
            if catalog is None or not catalog.is_current:
                raise AppException(status_code=400, code="AI_CHAT_PROVIDER_CATALOG_UNKNOWN", detail="目录中不存在当前供应商。")
            provider_key = catalog.provider_key
            protocol_key = catalog.protocol_key
            base_url = self._text(payload.base_url) or catalog.default_base_url
        else:
            provider_key = CUSTOM_PROVIDER_KEY
            protocol_key = CUSTOM_PROTOCOL_KEY
            base_url = self._required_base_url(payload.base_url)
        row = AiChatProviderConfig(
            user_id=None if payload.scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=payload.scope.value,
            name=payload.name.strip(),
            provider_key=provider_key,
            catalog_provider_key=catalog.provider_key if catalog else None,
            protocol_key=protocol_key,
            base_url=base_url,
            api_key_ciphertext=self.cipher.encrypt(self._text(payload.api_key)),
            status=RecordStatus.ACTIVE.value,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return await self._provider_item(row)

    async def update_provider(self, row_id: int, payload: ChatProviderConfigUpdate, *, operator_id: int) -> ChatProviderConfigItem:
        """更新名称、凭证和地址，目录身份与协议保持只读。"""

        row = await self._provider(row_id, editable=True)
        if payload.name is not None:
            row.name = payload.name.strip()
        if "base_url" in payload.model_fields_set:
            requested_base_url = self._text(payload.base_url)
            catalog = await self.session.get(AiChatProviderCatalog, row.catalog_provider_key) if row.catalog_provider_key else None
            row.base_url = requested_base_url or (catalog.default_base_url if catalog else None)
        if row.catalog_provider_key is None:
            row.base_url = self._required_base_url(row.base_url)
        if "api_key" in payload.model_fields_set:
            row.api_key_ciphertext = self.cipher.encrypt(self._text(payload.api_key))
        if payload.status is not None:
            row.status = payload.status
        row.updated_by = operator_id
        await self.session.commit()
        return await self._provider_item(row)

    async def delete_provider(self, row_id: int) -> None:
        """仅删除未被聊天模型引用的供应商连接。"""

        row = await self._provider(row_id, editable=True)
        linked = await self.session.scalar(select(AiChatModelConfig.id).where(AiChatModelConfig.provider_config_id == row.id).limit(1))
        if linked is not None:
            raise AppException(status_code=409, code="AI_CHAT_PROVIDER_IN_USE", detail="请先删除该供应商下的聊天模型。")
        await self.session.delete(row)
        await self.session.commit()

    async def list_models(self) -> list[ChatModelConfigItem]:
        """列出聊天模型，并按当前目录重新计算展示能力。"""

        rows = (await self.session.scalars(
            self._visible(AiChatModelConfig)
            .options(selectinload(AiChatModelConfig.provider_config))
            .order_by(AiChatModelConfig.updated_at.desc())
        )).all()
        return [await self._model_item(row) for row in rows]

    async def create_model(self, payload: ChatModelConfigCreate, *, operator_id: int) -> ChatModelConfigItem:
        """创建聊天模型；目录能力、覆盖与保守默认在服务端合并。"""

        self._require_scope_write(payload.scope)
        self._reject_e2e_mock_model(payload.model_id)
        provider = await self._provider(payload.provider_config_id, selectable=True)
        self._require_same_scope(payload.scope.value, provider.scope)
        capability, catalog_version = await self._resolve_capability(provider, payload.model_id, payload.capability_override)
        advanced = self._validate_advanced(payload.advanced_config)
        row = AiChatModelConfig(
            user_id=None if payload.scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=payload.scope.value,
            name=payload.name.strip(),
            provider_config_id=provider.id,
            model_id=payload.model_id.strip(),
            model_type="chat",
            reasoning_mode="auto",
            reasoning_level=None,
            supports_image_input=bool(capability["supports_image_input"]),
            context_window_tokens=int(capability["input_tokens"]),
            history_token_ratio=1.0,
            advanced_config_json=advanced,
            model_capability_json=self._legacy_capability_snapshot(provider, payload.model_id, capability),
            capability_override_json=dict(payload.capability_override),
            catalog_provider_key=provider.catalog_provider_key,
            catalog_version=catalog_version,
            status=RecordStatus.ACTIVE.value,
            created_by=operator_id,
            updated_by=operator_id,
        )
        row.provider_config = provider
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        row.provider_config = provider
        return await self._model_item(row)

    async def update_model(self, row_id: int, payload: ChatModelConfigUpdate, *, operator_id: int) -> ChatModelConfigItem:
        """更新聊天模型并刷新能力快照，已存在 Run 不受影响。"""

        row = await self._model(row_id, editable=True)
        provider = row.provider_config
        if payload.provider_config_id is not None:
            provider = await self._provider(payload.provider_config_id, selectable=True)
            self._require_same_scope(row.scope, provider.scope)
        model_id = payload.model_id.strip() if payload.model_id is not None else row.model_id
        self._reject_e2e_mock_model(model_id)
        override = payload.capability_override if payload.capability_override is not None else dict(row.capability_override_json or {})
        capability, catalog_version = await self._resolve_capability(provider, model_id, override)
        if payload.name is not None:
            row.name = payload.name.strip()
        row.provider_config_id = provider.id
        row.provider_config = provider
        row.model_id = model_id
        row.supports_image_input = bool(capability["supports_image_input"])
        row.context_window_tokens = int(capability["input_tokens"])
        row.model_capability_json = self._legacy_capability_snapshot(provider, model_id, capability)
        row.capability_override_json = override
        row.catalog_provider_key = provider.catalog_provider_key
        row.catalog_version = catalog_version
        if payload.advanced_config is not None:
            row.advanced_config_json = self._validate_advanced(payload.advanced_config)
        if payload.status is not None:
            row.status = payload.status
        row.updated_by = operator_id
        await self.session.commit()
        return await self._model_item(row)

    async def delete_model(self, row_id: int) -> None:
        """删除模型并移除聊天槽位绑定。"""

        row = await self._model(row_id, editable=True)
        await self.session.execute(delete(AiChatSlotBinding).where(AiChatSlotBinding.llm_config_id == row.id))
        await self.session.delete(row)
        await self.session.commit()

    async def get_binding(self, slot: str) -> ChatBindingItem:
        """读取个人绑定，未配置时回落到全局绑定。"""

        self._validate_chat_slot(slot)
        personal = await self._binding(slot, AiLlmConfigScope.PERSONAL.value, self.user_id)
        binding = personal or await self._binding(slot, AiLlmConfigScope.GLOBAL.value, None)
        return await self._binding_item(slot, binding, inherited=personal is None and binding is not None)

    async def update_binding(self, slot: str, payload: ChatBindingUpdate, *, operator_id: int) -> ChatBindingItem:
        """更新聊天槽位绑定，并验证模型硬能力。"""

        self._validate_chat_slot(slot)
        self._require_scope_write(payload.scope)
        user_id = None if payload.scope == AiLlmConfigScope.GLOBAL else self.user_id
        binding = await self._binding(slot, payload.scope.value, user_id)
        if payload.model_config_id is None:
            if binding:
                await self.session.delete(binding)
                await self.session.commit()
            return ChatBindingItem(slot=slot, binding_ready=False)
        model = await self._model(payload.model_config_id, selectable=True)
        self._require_same_scope(payload.scope.value, model.scope)
        capability, _ = await self._resolve_capability(model.provider_config, model.model_id, model.capability_override_json or {})
        self._validate_slot_capability(slot, capability)
        if binding is None:
            binding = AiChatSlotBinding(user_id=user_id, scope=payload.scope.value, slot=slot, created_by=operator_id)
            self.session.add(binding)
        binding.llm_config_id = model.id
        binding.llm_config = model
        binding.updated_by = operator_id
        await self.session.commit()
        return await self._binding_item(slot, binding, inherited=False)

    async def _resolve_capability(self, provider: AiChatProviderConfig, model_id: str, override: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """按用户覆盖、Models.dev、保守默认合并能力。"""

        catalog = None
        catalog_provider_key = getattr(provider, "catalog_provider_key", None)
        if catalog_provider_key:
            catalog = await self.session.scalar(select(AiChatModelCatalog).where(
                AiChatModelCatalog.provider_key == catalog_provider_key,
                AiChatModelCatalog.model_id == model_id,
            ))
        output_tokens = int(catalog.output_tokens or DEFAULT_OUTPUT_TOKENS) if catalog else DEFAULT_OUTPUT_TOKENS
        context_tokens = int(catalog.context_tokens or DEFAULT_CONTEXT_TOKENS) if catalog else DEFAULT_CONTEXT_TOKENS
        input_tokens = int(catalog.input_tokens or max(1, context_tokens - output_tokens)) if catalog else context_tokens - output_tokens
        capability: dict[str, Any] = {
            "context_tokens": context_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_modalities": list(catalog.input_modalities_json or []) if catalog else ["text"],
            "output_modalities": list(catalog.output_modalities_json or []) if catalog else ["text"],
            "supports_image_input": bool(catalog and "image" in (catalog.input_modalities_json or [])),
            "supports_tool_call": bool(catalog.supports_tool_call) if catalog else False,
            "supports_structured_output": bool(catalog.supports_structured_output) if catalog else False,
            "supports_attachment": bool(catalog.supports_attachment) if catalog else False,
            "supports_reasoning": bool(catalog.supports_reasoning) if catalog else False,
            "reasoning_options": dict(catalog.reasoning_options_json or {}) if catalog else {},
            "source": "models.dev" if catalog else "conservative_default",
            "verified": bool(catalog),
            "is_current": bool(catalog and catalog.is_current),
        }
        allowed = {
            "context_tokens", "input_tokens", "output_tokens", "input_modalities", "output_modalities",
            "supports_image_input", "supports_tool_call", "supports_structured_output", "supports_attachment",
            "supports_reasoning", "reasoning_options",
        }
        unknown = sorted(set(override) - allowed)
        if unknown:
            raise AppException(status_code=400, code="AI_CHAT_CAPABILITY_OVERRIDE_INVALID", detail=f"未知能力覆盖字段：{', '.join(unknown)}。")
        capability.update(override)
        for key in ("context_tokens", "input_tokens", "output_tokens"):
            value = capability.get(key)
            if not isinstance(value, int) or value <= 0:
                raise AppException(status_code=400, code="AI_CHAT_CAPABILITY_LIMIT_INVALID", detail=f"{key} 必须是正整数。")
        if capability["input_tokens"] + capability["output_tokens"] > capability["context_tokens"]:
            raise AppException(status_code=400, code="AI_CHAT_CAPABILITY_LIMIT_INVALID", detail="输入与输出上限之和不能超过 context。")
        return capability, catalog.catalog_version if catalog else None

    def _validate_policy(self, slot: str, protocol: str, capability: dict[str, Any], reasoning: ReasoningPolicy) -> None:
        """验证运行时推理策略；输入与输出预算统一由模型能力自动计算。"""

        self._validate_slot_capability(slot, capability)
        if reasoning.mode != "auto" and not capability["supports_reasoning"]:
            raise AppException(status_code=400, code="AI_CHAT_REASONING_UNSUPPORTED", detail="当前模型不支持显式推理策略。")
        model_controls = reasoning_control_types(capability.get("reasoning_options"))
        protocol_controls = protocol_reasoning_controls(protocol)
        if reasoning.mode != "auto" and not protocol_controls:
            raise AppException(status_code=400, code="AI_CHAT_REASONING_TRANSPORT_UNKNOWN", detail="当前协议连接仅支持自动推理策略。")
        if reasoning.mode == "disabled" and not supports_explicit_disable(capability.get("reasoning_options"), protocol):
            raise AppException(status_code=400, code="AI_CHAT_REASONING_DISABLE_UNSUPPORTED", detail="模型与协议不能共同保证关闭推理。")
        if reasoning.mode == "effort":
            options = reasoning_effort_options(capability.get("reasoning_options"))
            if "effort" not in model_controls.intersection(protocol_controls) or str(reasoning.value) not in options:
                raise AppException(status_code=400, code="AI_CHAT_REASONING_EFFORT_UNSUPPORTED", detail="推理强度不在当前目录模型公布的可用选项中。")
        if reasoning.mode == "budget_tokens" and "budget_tokens" not in model_controls.intersection(protocol_controls):
            raise AppException(status_code=400, code="AI_CHAT_REASONING_BUDGET_UNSUPPORTED", detail="当前协议不支持推理 token 预算。")
        if reasoning.mode == "budget_tokens":
            limits = reasoning_budget_limits(capability.get("reasoning_options"))
            value = int(reasoning.value or 0)
            if value < limits.get("min", 1) or (limits.get("max") is not None and value > limits["max"]):
                raise AppException(status_code=400, code="AI_CHAT_REASONING_BUDGET_INVALID", detail="推理 token 预算超出当前模型公布的范围。")
    @staticmethod
    def _validate_slot_capability(slot: str, capability: dict[str, Any]) -> None:
        """槽位只校验模型客观能力，不再保存运行策略。"""

        if slot == AiLlmSlot.AGENT_COORDINATOR.value and not capability["supports_tool_call"]:
            raise AppException(status_code=409, code="AI_CHAT_TOOL_CALL_REQUIRED", detail="内容助手只能绑定明确支持 tool call 的模型。")
        if slot == AiLlmSlot.IMAGE_UNDERSTANDING.value and not capability["supports_image_input"]:
            raise AppException(status_code=409, code="AI_CHAT_IMAGE_INPUT_REQUIRED", detail="图片理解槽位必须绑定支持图片输入的模型。")

    async def _provider_item(self, row: AiChatProviderConfig) -> ChatProviderConfigItem:
        """转换供应商响应并脱敏凭证。"""

        catalog = await self.session.get(AiChatProviderCatalog, row.catalog_provider_key) if row.catalog_provider_key else None
        secret = self.cipher.decrypt(row.api_key_ciphertext)
        return ChatProviderConfigItem(id=row.id, scope=row.scope, editable=self._editable(row.scope, row.user_id), name=row.name,
            provider_key=row.provider_key, catalog_provider_key=row.catalog_provider_key,
            provider_name=catalog.name if catalog else "自定义 OpenAI-compatible", protocol_key=row.protocol_key,
            base_url=row.base_url, has_api_key=bool(secret), api_key_masked=self.cipher.mask(secret) if secret else None, status=row.status)

    async def _model_item(self, row: AiChatModelConfig) -> ChatModelConfigItem:
        """转换模型响应，展示能力使用最新目录而非旧配置快照。"""

        capability, version = await self._resolve_capability(row.provider_config, row.model_id, row.capability_override_json or {})
        return ChatModelConfigItem(id=row.id, scope=row.scope, editable=self._editable(row.scope, row.user_id), name=row.name,
            provider_config_id=row.provider_config_id, provider_name=row.provider_config.name, provider_key=row.provider_config.provider_key,
            protocol_key=row.provider_config.protocol_key, model_id=row.model_id, catalog_version=version,
            capability=capability, capability_override=dict(row.capability_override_json or {}),
            advanced_config=dict(row.advanced_config_json or {}), status=row.status)

    async def _binding_item(self, slot: str, binding: AiChatSlotBinding | None, *, inherited: bool) -> ChatBindingItem:
        """转换绑定并计算自动预算。"""

        if binding is None or binding.llm_config is None:
            return ChatBindingItem(slot=slot, binding_ready=False)
        model = binding.llm_config
        capability, _ = await self._resolve_capability(model.provider_config, model.model_id, model.capability_override_json or {})
        ready = model.status == RecordStatus.ACTIVE.value and model.provider_config.status == RecordStatus.ACTIVE.value
        provider = model.provider_config
        catalog = await self.session.get(AiChatProviderCatalog, provider.catalog_provider_key) if provider.catalog_provider_key else None
        return ChatBindingItem(slot=slot, model_config_id=model.id, model_name=model.name,
            provider_config_id=provider.id, provider_config_name=provider.name, provider_key=provider.provider_key,
            provider_name=catalog.name if catalog else "自定义 OpenAI-compatible", model_id=model.model_id,
            supports_image_input=bool(capability["supports_image_input"]), binding_ready=ready,
            inherited_from_global=inherited)

    def _visible(self, model):  # noqa: ANN001
        """构造个人加全局可见查询。"""

        return select(model).where(or_(model.scope == AiLlmConfigScope.GLOBAL.value,
            (model.scope == AiLlmConfigScope.PERSONAL.value) & (model.user_id == self.user_id)))

    async def _provider(self, row_id: int, *, editable: bool = False, selectable: bool = False) -> AiChatProviderConfig:
        """读取并校验聊天供应商权限。"""

        row = await self.session.get(AiChatProviderConfig, row_id)
        if row is None or not self._readable(row.scope, row.user_id):
            raise AppException(status_code=404, code="AI_CHAT_PROVIDER_NOT_FOUND", detail="聊天供应商不存在。")
        if editable and not self._editable(row.scope, row.user_id):
            raise AppException(status_code=403, code="AI_CHAT_PROVIDER_READONLY", detail="当前聊天供应商不可编辑。")
        if selectable and row.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_CHAT_PROVIDER_DISABLED", detail="聊天供应商未启用。")
        return row

    async def _model(self, row_id: int, *, editable: bool = False, selectable: bool = False) -> AiChatModelConfig:
        """读取并校验聊天模型权限。"""

        row = await self.session.scalar(select(AiChatModelConfig).where(AiChatModelConfig.id == row_id).options(selectinload(AiChatModelConfig.provider_config)))
        if row is None or not self._readable(row.scope, row.user_id):
            raise AppException(status_code=404, code="AI_CHAT_MODEL_NOT_FOUND", detail="聊天模型不存在。")
        if editable and not self._editable(row.scope, row.user_id):
            raise AppException(status_code=403, code="AI_CHAT_MODEL_READONLY", detail="当前聊天模型不可编辑。")
        if selectable and (row.status != RecordStatus.ACTIVE.value or row.provider_config.status != RecordStatus.ACTIVE.value):
            raise AppException(status_code=409, code="AI_CHAT_MODEL_DISABLED", detail="聊天模型或供应商未启用。")
        return row

    async def _binding(self, slot: str, scope: str, user_id: int | None) -> AiChatSlotBinding | None:
        """读取绑定并预加载模型与供应商。"""

        return await self.session.scalar(select(AiChatSlotBinding).where(AiChatSlotBinding.slot == slot,
            AiChatSlotBinding.scope == scope, AiChatSlotBinding.user_id == user_id)
            .options(selectinload(AiChatSlotBinding.llm_config).selectinload(AiChatModelConfig.provider_config)))

    @staticmethod
    def _legacy_capability_snapshot(provider: AiChatProviderConfig, model_id: str, capability: dict[str, Any]) -> dict[str, Any]:
        """生成现有 Pydantic AI 运行器可读取的稳定能力快照。"""

        native_levels = reasoning_effort_options(capability.get("reasoning_options"))
        return {"profile_key": f"catalog:{provider.provider_key}:{model_id}", "profile_version": 3,
            "provider_key": provider.provider_key, "protocol_key": provider.protocol_key,
            "source": capability["source"], "verified": capability["verified"],
            "context_window_tokens": capability["context_tokens"], "model_max_output_tokens": capability["output_tokens"],
            "supports_image_input": capability["supports_image_input"], "supports_tool_call": capability["supports_tool_call"],
            "supports_reasoning": capability["supports_reasoning"],
            "reasoning_options": dict(capability.get("reasoning_options") or {}),
            "supports_explicit_disable": supports_explicit_disable(capability.get("reasoning_options"), provider.protocol_key),
            "supports_reasoning_budget": "budget_tokens" in reasoning_control_types(capability.get("reasoning_options")).intersection(protocol_reasoning_controls(provider.protocol_key)), "default_level": None,
            "native_levels": native_levels, "level_mapping": {item: item for item in native_levels}, "warnings": []}

    @staticmethod
    def _validate_advanced(value: dict[str, Any]) -> dict[str, Any]:
        """禁止高级参数覆盖协议、凭证、推理与预算受管字段。"""

        if not isinstance(value, dict):
            raise AppException(status_code=400, code="AI_CHAT_ADVANCED_INVALID", detail="高级配置必须是 JSON 对象。")
        conflicts = sorted(PROTECTED_ADVANCED_CONFIG_KEYS.intersection(value))
        if conflicts:
            raise AppException(status_code=400, code="AI_CHAT_ADVANCED_CONFLICT", detail=f"高级配置包含受管字段：{', '.join(conflicts)}。")
        return dict(value)

    def _require_scope_write(self, scope: AiLlmConfigScope) -> None:
        """全局配置仅平台管理员可写。"""

        if scope == AiLlmConfigScope.GLOBAL and self.user_role != UserRole.PLATFORM_ADMIN.value:
            raise AppException(status_code=403, code="AI_CHAT_GLOBAL_ADMIN_REQUIRED", detail="只有平台管理员可以维护全局模型。")

    def _readable(self, scope: str, owner: int | None) -> bool:
        return scope == AiLlmConfigScope.GLOBAL.value or owner == self.user_id

    def _editable(self, scope: str, owner: int | None) -> bool:
        return (scope == AiLlmConfigScope.GLOBAL.value and self.user_role == UserRole.PLATFORM_ADMIN.value) or owner == self.user_id

    @staticmethod
    def _require_same_scope(expected: str, actual: str) -> None:
        if expected != actual:
            raise AppException(status_code=409, code="AI_CHAT_SCOPE_MISMATCH", detail="供应商、模型和绑定必须属于同一配置范围。")

    @staticmethod
    def _validate_chat_slot(slot: str) -> None:
        if slot not in {AiLlmSlot.AGENT_COORDINATOR.value, AiLlmSlot.IMAGE_UNDERSTANDING.value}:
            raise AppException(status_code=400, code="AI_CHAT_SLOT_UNSUPPORTED", detail="当前槽位不是聊天模型槽位。")

    @staticmethod
    def _text(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @classmethod
    def _required_base_url(cls, value: str | None) -> str:
        normalized = cls._text(value)
        if not normalized:
            raise AppException(status_code=400, code="AI_CHAT_BASE_URL_REQUIRED", detail="自定义供应商必须填写 Base URL。")
        return normalized

    @staticmethod
    def _reject_e2e_mock_model(model_id: str) -> None:
        """生产数据库禁止创建仅供 E2E 分派器识别的 mock 模型。"""

        from app.ai.testing.scenarios import E2E_MOCK_MODEL_PREFIXES
        from app.core.testing_environment import require_e2e_database

        if any(str(model_id or "").strip().startswith(prefix) for prefix in E2E_MOCK_MODEL_PREFIXES):
            require_e2e_database()
