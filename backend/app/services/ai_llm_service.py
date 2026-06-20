"""文件功能：封装用户级大模型配置、供应商目录与固定槽位绑定的业务逻辑。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.provider_catalog import (
    LLM_SLOT_DEFINITIONS,
    MIMO_MAX_COMPLETION_TOKENS,
    PROTECTED_ADVANCED_CONFIG_KEYS,
    get_llm_provider_entry,
    get_llm_slot_definition,
    list_llm_provider_entries,
)
from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.enums import AiLlmConfigScope, RecordStatus, UserRole
from app.models.ai_llm import AiLlmConfig, AiLlmSlotBinding
from app.schemas.llm import (
    LLM_CONTEXT_WINDOW_TOKEN_DEFAULT,
    LLM_COMPRESSION_TARGET_RATIO_DEFAULT,
    LLM_MAX_OUTPUT_TOKEN_DEFAULT,
    LlmConfigCreateRequest,
    LlmConfigItem,
    LlmConfigUpdateRequest,
    LlmProviderCatalogItem,
    LlmSlotBindingItem,
    LlmSlotBindingUpdateRequest,
)


class AiLlmService:
    """统一管理用户级大模型配置、固定槽位绑定与供应商目录。"""

    def __init__(self, session: AsyncSession, *, user_id: int, user_role: str = UserRole.WORKSPACE_USER.value) -> None:
        self.session = session
        self.user_id = user_id
        self.user_role = user_role
        self._cipher = LlmSecretCipher()

    async def list_provider_catalog(self) -> list[LlmProviderCatalogItem]:
        """返回后端维护的可用供应商目录。"""

        return [
            LlmProviderCatalogItem(
                provider_key=item.provider_key,
                label=item.label,
                provider_adapter=item.provider_adapter,
                docs_url=item.docs_url,
                supports_base_url=item.supports_base_url,
                supports_api_key=item.supports_api_key,
                supports_thinking=item.supports_thinking,
                thinking_mode=item.thinking_mode,
                default_base_url=item.default_base_url,
                default_model_id=item.default_model_id,
                default_thinking_enabled=item.default_thinking_enabled,
                default_thinking_effort=item.default_thinking_effort,
                default_context_window_tokens=item.default_context_window_tokens,
                default_max_output_tokens=item.default_max_output_tokens,
                default_supports_image_input=item.default_supports_image_input,
                thinking_effort_options=list(item.thinking_effort_options),
                advanced_json_hint=item.advanced_json_hint or {},
            )
            for item in list_llm_provider_entries()
        ]

    async def list_configs(self) -> list[LlmConfigItem]:
        """列出当前用户可管理的全部大模型配置。"""

        statement = (
            select(AiLlmConfig)
            .where(
                (AiLlmConfig.scope == AiLlmConfigScope.GLOBAL.value)
                | (
                    (AiLlmConfig.scope == AiLlmConfigScope.PERSONAL.value)
                    & (AiLlmConfig.user_id == self.user_id)
                )
            )
            .order_by(AiLlmConfig.scope.asc(), AiLlmConfig.updated_at.desc(), AiLlmConfig.id.desc())
        )
        items = (await self.session.scalars(statement)).all()
        return [self._to_config_item(item) for item in items]

    async def get_config(self, config_id: int) -> LlmConfigItem:
        """读取单条大模型配置详情。"""

        config = await self._get_config_or_raise(config_id)
        return self._to_config_item(config)

    async def create_config(self, payload: LlmConfigCreateRequest, *, operator_id: int) -> LlmConfigItem:
        """创建当前用户的大模型配置。"""

        requested_scope = payload.scope
        if requested_scope == AiLlmConfigScope.GLOBAL and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_ADMIN_REQUIRED", detail="只有平台管理员可以维护全局模型。")

        provider_key = self._normalize_provider_key(payload.provider_key)
        base_url = self._normalize_optional_text(payload.base_url)
        api_key = self._normalize_optional_secret(payload.api_key)
        advanced_config = self._validate_advanced_config(payload.advanced_config_json)
        provider_entry = self._validate_provider_constraints(
            provider_key=provider_key,
            base_url=base_url,
            api_key=api_key,
            max_output_tokens=payload.max_output_tokens,
        )

        config = AiLlmConfig(
            user_id=None if requested_scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=requested_scope.value,
            name=payload.name.strip(),
            provider_key=provider_key,
            model_id=payload.model_id.strip(),
            base_url=base_url,
            api_key_ciphertext=self._cipher.encrypt(api_key),
            thinking_enabled=bool(payload.thinking_enabled and provider_entry.supports_thinking),
            thinking_effort=self._normalize_thinking_effort(provider_entry, payload.thinking_effort),
            supports_image_input=bool(payload.supports_image_input),
            context_window_tokens=payload.context_window_tokens,
            max_output_tokens=payload.max_output_tokens,
            history_token_ratio=payload.history_token_ratio,
            compression_target_ratio=payload.compression_target_ratio,
            advanced_config_json=advanced_config,
            status=RecordStatus.ACTIVE.value,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return self._to_config_item(config)

    async def update_config(
        self,
        config_id: int,
        payload: LlmConfigUpdateRequest,
        *,
        operator_id: int,
    ) -> LlmConfigItem:
        """更新当前用户的大模型配置。"""

        config = await self._get_config_or_raise(config_id)
        if config.scope == AiLlmConfigScope.GLOBAL.value and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_READONLY", detail="管理员全局模型不允许普通用户修改。")

        next_provider_key = self._normalize_provider_key(payload.provider_key or config.provider_key)
        next_name = payload.name.strip() if payload.name is not None else config.name
        next_model_id = payload.model_id.strip() if payload.model_id is not None else config.model_id
        next_base_url = (
            self._normalize_optional_text(payload.base_url) if payload.base_url is not None else config.base_url
        )
        next_advanced_config = (
            self._validate_advanced_config(payload.advanced_config_json)
            if payload.advanced_config_json is not None
            else self._validate_advanced_config(config.advanced_config_json or {})
        )
        next_max_output_tokens = payload.max_output_tokens if payload.max_output_tokens is not None else config.max_output_tokens

        current_api_key = self._cipher.decrypt(config.api_key_ciphertext)
        next_api_key = current_api_key
        if payload.api_key is not None:
            next_api_key = self._normalize_optional_secret(payload.api_key)

        provider_entry = self._validate_provider_constraints(
            provider_key=next_provider_key,
            base_url=next_base_url,
            api_key=next_api_key,
            max_output_tokens=next_max_output_tokens,
        )
        next_thinking_effort = config.thinking_effort
        if payload.thinking_effort is not None:
            next_thinking_effort = self._normalize_thinking_effort(provider_entry, payload.thinking_effort)
        elif next_provider_key != config.provider_key:
            next_thinking_effort = self._normalize_thinking_effort(provider_entry, config.thinking_effort)

        config.name = next_name
        config.provider_key = next_provider_key
        config.model_id = next_model_id
        config.base_url = next_base_url
        config.api_key_ciphertext = self._cipher.encrypt(next_api_key)
        config.thinking_enabled = (
            bool(payload.thinking_enabled and provider_entry.supports_thinking)
            if payload.thinking_enabled is not None
            else bool(config.thinking_enabled and provider_entry.supports_thinking)
        )
        config.thinking_effort = next_thinking_effort if provider_entry.supports_thinking else None
        if payload.supports_image_input is not None:
            config.supports_image_input = bool(payload.supports_image_input)
        if payload.context_window_tokens is not None:
            config.context_window_tokens = payload.context_window_tokens
        if payload.max_output_tokens is not None:
            config.max_output_tokens = next_max_output_tokens
        if payload.history_token_ratio is not None:
            config.history_token_ratio = payload.history_token_ratio
        if payload.compression_target_ratio is not None:
            config.compression_target_ratio = payload.compression_target_ratio
        config.advanced_config_json = next_advanced_config
        if payload.status is not None:
            config.status = payload.status
        config.updated_by = operator_id

        await self.session.commit()
        await self.session.refresh(config)
        return self._to_config_item(config)

    async def list_slot_bindings(self) -> list[LlmSlotBindingItem]:
        """列出当前用户全部固定槽位的绑定状态。"""

        binding_map = await self.get_slot_binding_lookup()
        return [binding_map[slot] for slot in LLM_SLOT_DEFINITIONS]

    async def get_slot_binding(self, slot: str) -> LlmSlotBindingItem:
        """读取单个固定槽位的绑定状态。"""

        binding_map = await self.get_slot_binding_lookup()
        definition = get_llm_slot_definition(slot)
        return binding_map.get(slot) or LlmSlotBindingItem(
            slot=definition.slot,
            slot_label=definition.label,
            binding_ready=False,
        )

    async def update_slot_binding(
        self,
        slot: str,
        payload: LlmSlotBindingUpdateRequest,
        *,
        operator_id: int,
    ) -> LlmSlotBindingItem:
        """更新固定槽位与模型配置之间的绑定关系。"""

        definition = get_llm_slot_definition(slot)
        binding_scope = payload.scope
        if binding_scope == AiLlmConfigScope.GLOBAL and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_ADMIN_REQUIRED", detail="只有平台管理员可以维护全局默认模型。")
        binding_user_id = None if binding_scope == AiLlmConfigScope.GLOBAL else self.user_id
        binding = await self._get_slot_binding_model(slot, scope=binding_scope, user_id=binding_user_id)

        if payload.llm_config_id is None:
            if binding is not None:
                await self.session.delete(binding)
                await self.session.commit()
            return LlmSlotBindingItem(
                slot=definition.slot,
                slot_label=definition.label,
                binding_ready=False,
            )

        config = await self._get_selectable_config_or_raise(payload.llm_config_id)
        if binding_scope == AiLlmConfigScope.GLOBAL and config.scope != AiLlmConfigScope.GLOBAL.value:
            raise AppException(status_code=409, code="AI_LLM_GLOBAL_SLOT_REQUIRES_GLOBAL_CONFIG", detail="全局默认槽位只能绑定管理员全局模型。")
        if config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_LLM_CONFIG_DISABLED", detail="只能绑定启用中的大模型配置。")

        if binding is None:
            binding = AiLlmSlotBinding(
                user_id=binding_user_id,
                scope=binding_scope.value,
                slot=slot,
                llm_config_id=config.id,
                created_by=operator_id,
                updated_by=operator_id,
            )
            self.session.add(binding)
        else:
            binding.llm_config_id = config.id
            binding.updated_by = operator_id

        await self.session.commit()
        return await self.get_slot_binding(slot)

    async def get_bound_config_or_raise(self, slot: str) -> AiLlmConfig:
        """读取指定槽位当前绑定且可用的大模型配置，个人未绑定时回落全局默认。"""

        binding = await self._get_slot_binding_model(slot, scope=AiLlmConfigScope.PERSONAL, user_id=self.user_id)
        if binding is None or binding.llm_config is None:
            binding = await self._get_slot_binding_model(slot, scope=AiLlmConfigScope.GLOBAL, user_id=None)
        if binding is None or binding.llm_config is None:
            raise AppException(
                status_code=409,
                code="AI_LLM_SLOT_UNBOUND",
                detail="当前智能体未绑定模型，请前往AI设置绑定后重试。",
            )
        if binding.llm_config.status != RecordStatus.ACTIVE.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_SLOT_UNBOUND",
                detail="当前智能体槽位绑定的大模型配置不可用，请重新绑定。",
            )
        return binding.llm_config

    async def get_slot_binding_lookup(self) -> dict[str, LlmSlotBindingItem]:
        """按槽位返回当前用户全部绑定状态，便于复用到 Agent 列表接口。"""

        personal_bindings = (await self.session.scalars(
            select(AiLlmSlotBinding)
            .where(
                AiLlmSlotBinding.scope == AiLlmConfigScope.PERSONAL.value,
                AiLlmSlotBinding.user_id == self.user_id,
            )
            .options(selectinload(AiLlmSlotBinding.llm_config))
        )).all()
        global_bindings = (await self.session.scalars(
            select(AiLlmSlotBinding)
            .where(
                AiLlmSlotBinding.scope == AiLlmConfigScope.GLOBAL.value,
                AiLlmSlotBinding.user_id.is_(None),
            )
            .options(selectinload(AiLlmSlotBinding.llm_config))
        )).all()
        result: dict[str, LlmSlotBindingItem] = {}

        for slot, definition in LLM_SLOT_DEFINITIONS.items():
            result[slot] = LlmSlotBindingItem(
                slot=slot,
                slot_label=definition.label,
                binding_ready=False,
            )

        for binding in global_bindings:
            self._apply_binding_to_lookup(result, binding, inherited_from_global=True)
        for binding in personal_bindings:
            self._apply_binding_to_lookup(result, binding, inherited_from_global=False)
        return result

    def _apply_binding_to_lookup(
        self,
        result: dict[str, LlmSlotBindingItem],
        binding: AiLlmSlotBinding,
        *,
        inherited_from_global: bool,
    ) -> None:
        """把槽位绑定折叠进响应映射，个人绑定覆盖全局默认。"""

        definition = LLM_SLOT_DEFINITIONS.get(binding.slot)
        if definition is None:
            return
        config = binding.llm_config
        provider_entry = get_llm_provider_entry(config.provider_key) if config is not None else None
        result[binding.slot] = LlmSlotBindingItem(
            slot=binding.slot,
            slot_label=definition.label,
            llm_config_id=config.id if config is not None else None,
            llm_config_name=config.name if config is not None else None,
            provider_key=config.provider_key if config is not None else None,
            provider_label=provider_entry.label if provider_entry is not None else None,
            model_id=config.model_id if config is not None else None,
            binding_ready=bool(config is not None and config.status == RecordStatus.ACTIVE.value),
            supports_image_input=bool(config.supports_image_input) if config is not None else False,
            inherited_from_global=inherited_from_global,
        )

    async def _get_config_or_raise(self, config_id: int) -> AiLlmConfig:
        """按主键读取当前用户可管理的大模型配置。"""

        statement = select(AiLlmConfig).where(AiLlmConfig.id == config_id)
        config = await self.session.scalar(statement)
        if config is None or not self._can_read_config(config):
            raise AppException(status_code=404, code="AI_LLM_CONFIG_NOT_FOUND", detail="大模型配置不存在。")
        return config

    async def _get_selectable_config_or_raise(self, config_id: int) -> AiLlmConfig:
        """读取当前用户可绑定的大模型配置。"""

        config = await self._get_config_or_raise(config_id)
        if config.scope == AiLlmConfigScope.PERSONAL.value and config.user_id != self.user_id:
            raise AppException(status_code=404, code="AI_LLM_CONFIG_NOT_FOUND", detail="大模型配置不存在。")
        return config

    async def _get_slot_binding_model(
        self,
        slot: str,
        *,
        scope: AiLlmConfigScope,
        user_id: int | None,
    ) -> AiLlmSlotBinding | None:
        """按槽位读取当前用户的绑定记录。"""

        statement = (
            select(AiLlmSlotBinding)
            .where(
                AiLlmSlotBinding.scope == scope.value,
                AiLlmSlotBinding.user_id.is_(None) if user_id is None else AiLlmSlotBinding.user_id == user_id,
                AiLlmSlotBinding.slot == slot,
            )
            .options(selectinload(AiLlmSlotBinding.llm_config))
        )
        return await self.session.scalar(statement)

    def _to_config_item(self, config: AiLlmConfig) -> LlmConfigItem:
        """把 ORM 模型转换为前端可消费的配置详情。"""

        provider_entry = get_llm_provider_entry(config.provider_key)
        raw_api_key = self._cipher.decrypt(config.api_key_ciphertext)
        editable = self._can_edit_config(config)
        return LlmConfigItem(
            id=config.id,
            scope=AiLlmConfigScope(config.scope),
            owner_user_id=config.user_id,
            editable=editable,
            name=config.name,
            provider_key=config.provider_key,
            provider_label=provider_entry.label,
            model_id=config.model_id,
            base_url=config.base_url,
            thinking_enabled=bool(config.thinking_enabled and provider_entry.supports_thinking),
            thinking_effort=config.thinking_effort,
            supports_image_input=bool(config.supports_image_input),
            context_window_tokens=int(config.context_window_tokens or LLM_CONTEXT_WINDOW_TOKEN_DEFAULT),
            max_output_tokens=int(config.max_output_tokens or LLM_MAX_OUTPUT_TOKEN_DEFAULT),
            history_token_ratio=float(config.history_token_ratio if config.history_token_ratio is not None else 0.5),
            compression_target_ratio=float(
                config.compression_target_ratio
                if config.compression_target_ratio is not None
                else LLM_COMPRESSION_TARGET_RATIO_DEFAULT
            ),
            advanced_config_json=self._validate_advanced_config(config.advanced_config_json or {}),
            status=config.status,
            has_api_key=bool(raw_api_key),
            api_key_masked=self._cipher.mask(raw_api_key) if editable or config.scope == AiLlmConfigScope.GLOBAL.value else None,
            created_at=config.created_at.isoformat() if config.created_at is not None else None,
            updated_at=config.updated_at.isoformat() if config.updated_at is not None else None,
        )

    @property
    def _is_platform_admin(self) -> bool:
        """判断当前用户是否为平台管理员。"""

        return self.user_role == UserRole.PLATFORM_ADMIN.value

    def _can_read_config(self, config: AiLlmConfig) -> bool:
        """判断当前用户是否可读取模型配置。"""

        if config.scope == AiLlmConfigScope.GLOBAL.value:
            return True
        return config.user_id == self.user_id

    def _can_edit_config(self, config: AiLlmConfig) -> bool:
        """判断当前用户是否可编辑模型配置。"""

        if config.scope == AiLlmConfigScope.GLOBAL.value:
            return self._is_platform_admin
        return config.user_id == self.user_id

    @staticmethod
    def _normalize_provider_key(provider_key: str) -> str:
        """归一化供应商键值。"""

        return provider_key.strip().lower()

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """归一化可选文本字段，空串视为未填写。"""

        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _normalize_optional_secret(value: str | None) -> str | None:
        """归一化可选密钥字段，空串表示清空。"""

        normalized = str(value or "").strip()
        return normalized or None

    def _normalize_thinking_effort(self, provider_entry, value: str | None) -> str | None:
        """归一化用户填写的思考强度；具体可用性由供应商接口决定。"""

        if not provider_entry.supports_thinking:
            return None
        normalized = str(value or "").strip().lower()
        return normalized or None

    def _validate_provider_constraints(
        self,
        *,
        provider_key: str,
        base_url: str | None,
        api_key: str | None,
        max_output_tokens: int | None = None,
    ):
        """校验供应商公共字段是否满足目录约束。"""

        entry = get_llm_provider_entry(provider_key)
        if base_url and not entry.supports_base_url:
            raise AppException(
                status_code=400,
                code="AI_LLM_BASE_URL_UNSUPPORTED",
                detail="当前供应商不支持自定义 Base URL。",
            )
        if api_key and not entry.supports_api_key:
            raise AppException(
                status_code=400,
                code="AI_LLM_API_KEY_UNSUPPORTED",
                detail="当前供应商不支持自定义 API Key。",
            )
        if provider_key == "mimo" and max_output_tokens and max_output_tokens > MIMO_MAX_COMPLETION_TOKENS:
            raise AppException(
                status_code=400,
                code="AI_LLM_MAX_OUTPUT_TOKENS_UNSUPPORTED",
                detail=f"MiMo 模型最大输出 tokens 不能超过 {MIMO_MAX_COMPLETION_TOKENS}。",
            )
        return entry

    @staticmethod
    def _validate_advanced_config(value: dict[str, Any]) -> dict[str, Any]:
        """限制高级配置必须是对象且不能覆盖受管字段。"""

        if not isinstance(value, dict):
            raise AppException(status_code=400, code="AI_LLM_ADVANCED_CONFIG_INVALID", detail="高级配置必须是 JSON 对象。")
        conflicted_keys = sorted(key for key in value if key in PROTECTED_ADVANCED_CONFIG_KEYS)
        if conflicted_keys:
            raise AppException(
                status_code=400,
                code="AI_LLM_ADVANCED_CONFIG_CONFLICT",
                detail=f"高级配置禁止覆盖受管字段：{', '.join(conflicted_keys)}。",
            )
        return dict(value)
