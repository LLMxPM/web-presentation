"""文件功能：封装用户级大模型供应商配置、模型配置与固定槽位绑定的业务逻辑。"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import delete, select
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
from app.ai.model_capabilities import capability_from_snapshot, resolve_model_capability
from app.ai.model_budget import ModelRunBudget, derive_model_run_budget
from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_llm import AiLlmConfig, AiLlmProviderConfig, AiLlmSlotBinding
from app.models.enums import AiLlmConfigScope, AiLlmSlot, AiModelType, AiReasoningMode, RecordStatus, UserRole
from app.schemas.llm import (
    LLM_CONTEXT_WINDOW_TOKEN_DEFAULT,
    LLM_CONTEXT_WINDOW_TOKEN_MIN,
    LlmConfigCreateRequest,
    LlmConfigItem,
    LlmConfigUpdateRequest,
    LlmModelCapabilityItem,
    LlmProviderCatalogItem,
    LlmProviderConfigCreateRequest,
    LlmProviderConfigItem,
    LlmProviderConfigUpdateRequest,
    LlmSlotBindingItem,
    LlmSlotBindingUpdateRequest,
)
from app.schemas.model_config import ReasoningPolicy
from app.services.image_generation.contracts import validate_advanced_options
from app.services.image_generation.registry import (
    get_image_model_spec,
    validate_image_provider_connection,
)


class AiLlmService:
    """统一管理用户级大模型供应商配置、模型参数配置和固定槽位绑定。"""

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
                provider_type=AiModelType(item.provider_type),
                provider_adapter=item.provider_adapter,
                docs_url=item.docs_url,
                supports_base_url=item.supports_base_url,
                requires_base_url=item.requires_base_url,
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
                supported_model_types=list(item.supported_model_types),
                default_image_generation_model_id=item.default_image_generation_model_id,
                base_url_hint=item.base_url_hint,
                thinking_effort_options=list(item.thinking_effort_options),
                advanced_json_hint=item.advanced_json_hint or {},
                image_generation_models=list(item.image_generation_models),
            )
            for item in list_llm_provider_entries()
        ]

    async def resolve_model_capability_item(
        self,
        provider_config_id: int,
        model_id: str,
        *,
        override: dict[str, Any] | None = None,
    ) -> LlmModelCapabilityItem:
        """解析模型能力并返回平台四档到供应商原生值的映射。"""

        provider_config = await self._get_provider_config_or_raise(provider_config_id)
        if provider_config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_LLM_PROVIDER_CONFIG_DISABLED", detail="只能解析启用中的供应商配置。")
        entry = get_llm_provider_entry(provider_config.provider_key)
        capability = resolve_model_capability(
            provider_config.provider_key,
            model_id,
            default_context_window_tokens=entry.default_context_window_tokens,
            default_model_max_output_tokens=entry.default_max_output_tokens,
            default_supports_image_input=entry.default_supports_image_input,
            override=override,
        )
        item = capability.as_dict()
        suggested_input_tokens = self._recommended_usable_input_tokens(capability, provider_config.provider_key)
        run_budget = derive_model_run_budget(
            suggested_input_tokens,
            provider_output_limit=self._model_output_limit(capability.profile.model_max_output_tokens, provider_config.provider_key),
        )
        warnings = list(item["warnings"])
        if not capability.profile.verified:
            warnings.append(f"请确认模型至少支持 {run_budget.required_model_context_tokens} tokens 总上下文。")
        return LlmModelCapabilityItem(
            source=str(item["source"]), verified=bool(item["verified"]), profile_key=str(item["profile_key"]),
            profile_version=int(item["profile_version"]), context_window_tokens=suggested_input_tokens,
            model_context_window_tokens=int(item["context_window_tokens"]) if capability.profile.source != "provider_default" else None,
            model_max_output_tokens=int(item["model_max_output_tokens"]),
            required_model_context_tokens=run_budget.required_model_context_tokens,
            request_output_tokens=run_budget.max_output_tokens,
            runtime_headroom_tokens=run_budget.runtime_headroom_tokens,
            compression_trigger_tokens=run_budget.compression_trigger_tokens,
            compression_target_tokens=run_budget.compression_target_tokens,
            budget_policy_version=run_budget.budget_policy_version,
            request_max_output_tokens=run_budget.max_output_tokens,
            supports_image_input=bool(item["supports_image_input"]), supports_reasoning=bool(item["supports_reasoning"]),
            supports_explicit_disable=bool(item["supports_explicit_disable"]), default_level=item.get("default_level"),
            level_mapping=dict(item["level_mapping"]), warnings=warnings,
        )

    async def list_provider_configs(self) -> list[LlmProviderConfigItem]:
        """列出当前用户可见的供应商凭证配置。"""

        statement = (
            select(AiLlmProviderConfig)
            .where(
                (AiLlmProviderConfig.scope == AiLlmConfigScope.GLOBAL.value)
                | (
                    (AiLlmProviderConfig.scope == AiLlmConfigScope.PERSONAL.value)
                    & (AiLlmProviderConfig.user_id == self.user_id)
                )
            )
            .order_by(AiLlmProviderConfig.scope.asc(), AiLlmProviderConfig.updated_at.desc(), AiLlmProviderConfig.id.desc())
        )
        items = (await self.session.scalars(statement)).all()
        return [self._to_provider_config_item(item) for item in items]

    async def get_provider_config(self, provider_config_id: int) -> LlmProviderConfigItem:
        """读取单条供应商配置详情。"""

        config = await self._get_provider_config_or_raise(provider_config_id)
        return self._to_provider_config_item(config)

    async def create_provider_config(
        self,
        payload: LlmProviderConfigCreateRequest,
        *,
        operator_id: int,
    ) -> LlmProviderConfigItem:
        """创建当前用户可复用的供应商凭证配置。"""

        requested_scope = payload.scope
        if requested_scope == AiLlmConfigScope.GLOBAL and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_ADMIN_REQUIRED", detail="只有平台管理员可以维护全局供应商。")

        provider_key = self._normalize_provider_key(payload.provider_key)
        base_url = self._normalize_optional_text(payload.base_url)
        api_key = self._normalize_optional_secret(payload.api_key)
        self._validate_provider_constraints(provider_key=provider_key, base_url=base_url, api_key=api_key)

        config = AiLlmProviderConfig(
            user_id=None if requested_scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=requested_scope.value,
            name=payload.name.strip(),
            provider_key=provider_key,
            base_url=base_url,
            api_key_ciphertext=self._cipher.encrypt(api_key),
            status=RecordStatus.ACTIVE.value,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return self._to_provider_config_item(config)

    async def update_provider_config(
        self,
        provider_config_id: int,
        payload: LlmProviderConfigUpdateRequest,
        *,
        operator_id: int,
    ) -> LlmProviderConfigItem:
        """更新当前用户可编辑的供应商凭证配置。"""

        config = await self._get_provider_config_or_raise(provider_config_id)
        if config.scope == AiLlmConfigScope.GLOBAL.value and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_READONLY", detail="管理员全局供应商不允许普通用户修改。")

        fields_set = payload.model_fields_set
        if "status" in fields_set:
            raise AppException(
                status_code=400,
                code="AI_LLM_PROVIDER_STATUS_UPDATE_UNSUPPORTED",
                detail="供应商不再支持归档或恢复；请先删除关联模型，再直接删除供应商。",
            )
        next_base_url = self._normalize_optional_text(payload.base_url) if "base_url" in fields_set else config.base_url
        current_api_key = self._cipher.decrypt(config.api_key_ciphertext)
        next_api_key = self._normalize_optional_secret(payload.api_key) if "api_key" in fields_set else current_api_key
        self._validate_provider_constraints(
            provider_key=config.provider_key,
            base_url=next_base_url,
            api_key=next_api_key,
        )

        if payload.name is not None:
            config.name = payload.name.strip()
        config.base_url = next_base_url
        config.api_key_ciphertext = self._cipher.encrypt(next_api_key)
        config.updated_by = operator_id

        await self.session.commit()
        await self.session.refresh(config)
        return self._to_provider_config_item(config)

    async def delete_provider_config(self, provider_config_id: int) -> None:
        """硬删除供应商配置；删除前必须确认没有任何模型仍引用它。"""

        config = await self._get_provider_config_or_raise(provider_config_id)
        if not self._can_edit_provider_config(config):
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_READONLY", detail="管理员全局供应商不允许普通用户删除。")

        linked_config_id = await self.session.scalar(
            select(AiLlmConfig.id)
            .where(AiLlmConfig.provider_config_id == config.id)
            .limit(1)
        )
        if linked_config_id is not None:
            raise AppException(
                status_code=409,
                code="AI_LLM_PROVIDER_CONFIG_IN_USE",
                detail="当前供应商仍被模型引用，请先删除关联模型。",
            )

        await self.session.delete(config)
        await self.session.commit()

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
            .options(selectinload(AiLlmConfig.provider_config))
            .order_by(AiLlmConfig.scope.asc(), AiLlmConfig.updated_at.desc(), AiLlmConfig.id.desc())
        )
        items = (await self.session.scalars(statement)).all()
        return [self._to_config_item(item) for item in items]

    async def get_config(self, config_id: int) -> LlmConfigItem:
        """读取单条大模型配置详情。"""

        config = await self._get_config_or_raise(config_id)
        return self._to_config_item(config)

    async def create_config(self, payload: LlmConfigCreateRequest, *, operator_id: int) -> LlmConfigItem:
        """创建当前用户的大模型参数配置。"""

        requested_scope = payload.scope
        if requested_scope == AiLlmConfigScope.GLOBAL and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_ADMIN_REQUIRED", detail="只有平台管理员可以维护全局模型。")
        self._reject_e2e_mock_model_outside_e2e_database(payload.model_id)

        provider_config = await self._get_selectable_provider_config_or_raise(
            payload.provider_config_id,
            scope=requested_scope,
            require_active=True,
        )
        provider_entry = self._validate_provider_constraints(
            provider_key=provider_config.provider_key,
            base_url=provider_config.base_url,
            api_key=self._cipher.decrypt(provider_config.api_key_ciphertext),
        )
        self._validate_provider_model_type(provider_entry, payload.model_type.value)
        advanced_config = self._validate_model_advanced_config(
            provider_key=provider_config.provider_key,
            model_id=payload.model_id.strip(),
            model_type=payload.model_type.value,
            value=payload.advanced_config_json,
        )
        is_chat_model = payload.model_type == AiModelType.CHAT
        base_capability = resolve_model_capability(
            provider_config.provider_key,
            payload.model_id,
            default_context_window_tokens=provider_entry.default_context_window_tokens,
            default_model_max_output_tokens=provider_entry.default_max_output_tokens,
            default_supports_image_input=provider_entry.default_supports_image_input,
        )
        capability_override = dict(payload.model_capability_override or {})
        if (
            "supports_image_input" in payload.model_fields_set
            and payload.supports_image_input != base_capability.profile.supports_image_input
        ):
            capability_override["supports_image_input"] = payload.supports_image_input
        capability = (
            resolve_model_capability(
                provider_config.provider_key,
                payload.model_id,
                default_context_window_tokens=provider_entry.default_context_window_tokens,
                default_model_max_output_tokens=provider_entry.default_max_output_tokens,
                default_supports_image_input=provider_entry.default_supports_image_input,
                override=capability_override,
            )
            if capability_override
            else base_capability
        )
        reasoning_mode = payload.reasoning_mode.value if payload.reasoning_mode is not None else AiReasoningMode.AUTO.value
        reasoning_level = payload.reasoning_level.value if payload.reasoning_level is not None else None
        if is_chat_model:
            self._validate_reasoning_policy(capability, reasoning_mode)
        usable_input_tokens = payload.context_window_tokens or self._recommended_usable_input_tokens(
            capability,
            provider_config.provider_key,
        )
        run_budget = derive_model_run_budget(
            usable_input_tokens,
            provider_output_limit=self._model_output_limit(capability.profile.model_max_output_tokens, provider_config.provider_key),
        )
        if is_chat_model:
            self._validate_model_context_capacity(capability, run_budget)

        config = AiLlmConfig(
            user_id=None if requested_scope == AiLlmConfigScope.GLOBAL else self.user_id,
            scope=requested_scope.value,
            name=payload.name.strip(),
            provider_config_id=provider_config.id,
            provider_config=provider_config,
            model_id=payload.model_id.strip(),
            model_type=payload.model_type.value,
            reasoning_mode=reasoning_mode if is_chat_model and provider_entry.supports_thinking else AiReasoningMode.AUTO.value,
            reasoning_level=reasoning_level if is_chat_model and reasoning_mode == AiReasoningMode.ENABLED.value else None,
            supports_image_input=bool(capability.profile.supports_image_input and is_chat_model),
            context_window_tokens=usable_input_tokens,
            history_token_ratio=1.0,
            advanced_config_json=advanced_config,
            model_capability_json={**capability.as_dict(), "provider_key": provider_config.provider_key},
            status=RecordStatus.ACTIVE.value,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        config.provider_config = provider_config
        return self._to_config_item(config)

    async def update_config(
        self,
        config_id: int,
        payload: LlmConfigUpdateRequest,
        *,
        operator_id: int,
    ) -> LlmConfigItem:
        """更新当前用户的大模型参数配置。"""

        config = await self._get_config_or_raise(config_id)
        if config.scope == AiLlmConfigScope.GLOBAL.value and not self._is_platform_admin:
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_READONLY", detail="管理员全局模型不允许普通用户修改。")
        await self._ensure_config_not_used_by_active_run(config.id)

        if "status" in payload.model_fields_set:
            raise AppException(
                status_code=400,
                code="AI_LLM_CONFIG_STATUS_UPDATE_UNSUPPORTED",
                detail="大模型不再支持归档或恢复；请直接删除模型。",
            )

        scope = AiLlmConfigScope(config.scope)
        if (
            payload.model_type is not None
            and payload.model_type.value != config.model_type
            and payload.provider_config_id is None
        ):
            raise AppException(
                status_code=400,
                code="AI_LLM_PROVIDER_MODEL_TYPE_MISMATCH",
                detail="修改模型类型时必须同时选择匹配类型的供应商配置。",
            )
        next_provider_config = config.provider_config
        if payload.provider_config_id is not None:
            next_provider_config = await self._get_selectable_provider_config_or_raise(
                payload.provider_config_id,
                scope=scope,
                require_active=True,
            )
        elif next_provider_config.status != RecordStatus.ACTIVE.value and payload.status != RecordStatus.ARCHIVED.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_PROVIDER_CONFIG_DISABLED",
                detail="当前模型引用的供应商配置不可用，请先更换供应商配置。",
            )

        next_name = payload.name.strip() if payload.name is not None else config.name
        next_model_id = payload.model_id.strip() if payload.model_id is not None else config.model_id
        self._reject_e2e_mock_model_outside_e2e_database(next_model_id)
        next_model_type = payload.model_type.value if payload.model_type is not None else config.model_type
        provider_entry = get_llm_provider_entry(next_provider_config.provider_key)
        base_capability = resolve_model_capability(
            next_provider_config.provider_key,
            next_model_id,
            default_context_window_tokens=provider_entry.default_context_window_tokens,
            default_model_max_output_tokens=provider_entry.default_max_output_tokens,
            default_supports_image_input=provider_entry.default_supports_image_input,
        )
        capability_override = dict(payload.model_capability_override or {})
        if (
            payload.supports_image_input is not None
            and payload.supports_image_input != base_capability.profile.supports_image_input
        ):
            capability_override["supports_image_input"] = payload.supports_image_input
        stored_capability = capability_from_snapshot(config.model_capability_json or {})
        capability_inputs_changed = (
            bool(capability_override)
            or "model_capability_override" in payload.model_fields_set
            or next_model_id != config.model_id
            or next_provider_config.id != config.provider_config_id
        )
        capability = (
            resolve_model_capability(
                next_provider_config.provider_key,
                next_model_id,
                default_context_window_tokens=provider_entry.default_context_window_tokens,
                default_model_max_output_tokens=provider_entry.default_max_output_tokens,
                default_supports_image_input=provider_entry.default_supports_image_input,
                override=capability_override,
            )
            if capability_override
            else base_capability
        ) if capability_inputs_changed or stored_capability is None else stored_capability
        next_context_window_tokens = payload.context_window_tokens if payload.context_window_tokens is not None else config.context_window_tokens
        run_budget = derive_model_run_budget(
            next_context_window_tokens,
            provider_output_limit=self._model_output_limit(capability.profile.model_max_output_tokens, next_provider_config.provider_key),
        )
        if next_model_type == AiModelType.CHAT.value:
            self._validate_model_context_capacity(capability, run_budget)

        provider_entry = self._validate_provider_constraints(
            provider_key=next_provider_config.provider_key,
            base_url=next_provider_config.base_url,
            api_key=self._cipher.decrypt(next_provider_config.api_key_ciphertext),
            max_output_tokens=run_budget.max_output_tokens,
        )
        self._validate_provider_model_type(provider_entry, next_model_type)
        next_advanced_config = (
            self._validate_model_advanced_config(
                provider_key=next_provider_config.provider_key,
                model_id=next_model_id,
                model_type=next_model_type,
                value=payload.advanced_config_json,
            )
            if payload.advanced_config_json is not None
            else self._validate_model_advanced_config(
                provider_key=next_provider_config.provider_key,
                model_id=next_model_id,
                model_type=next_model_type,
                value=self._sanitize_stored_advanced_config(config.advanced_config_json or {}),
            )
        )
        next_reasoning_mode = payload.reasoning_mode.value if payload.reasoning_mode is not None else config.reasoning_mode
        next_reasoning_level = (
            payload.reasoning_level.value if payload.reasoning_level is not None else None
        ) if "reasoning_level" in payload.model_fields_set else config.reasoning_level
        if next_reasoning_mode != AiReasoningMode.ENABLED.value:
            next_reasoning_level = None
        elif next_reasoning_level is None:
            next_reasoning_level = capability.profile.default_level or "medium"
        if next_model_type == AiModelType.CHAT.value:
            self._validate_reasoning_policy(capability, next_reasoning_mode)

        config.name = next_name
        config.provider_config_id = next_provider_config.id
        config.provider_config = next_provider_config
        config.model_id = next_model_id
        config.model_type = next_model_type
        is_chat_model = next_model_type == AiModelType.CHAT.value
        config.reasoning_mode = next_reasoning_mode if is_chat_model and provider_entry.supports_thinking else AiReasoningMode.AUTO.value
        config.reasoning_level = next_reasoning_level if is_chat_model and config.reasoning_mode == AiReasoningMode.ENABLED.value else None
        config.supports_image_input = bool(capability.profile.supports_image_input and is_chat_model)
        config.context_window_tokens = next_context_window_tokens
        config.history_token_ratio = 1.0
        config.advanced_config_json = next_advanced_config
        config.model_capability_json = {**capability.as_dict(), "provider_key": next_provider_config.provider_key}
        config.updated_by = operator_id

        await self.session.commit()
        await self.session.refresh(config)
        config.provider_config = next_provider_config
        return self._to_config_item(config)

    async def delete_config(self, config_id: int) -> None:
        """硬删除大模型配置，并同步移除引用该模型的固定槽位绑定。"""

        config = await self._get_config_or_raise(config_id)
        if not self._can_edit_config(config):
            raise AppException(status_code=403, code="AI_LLM_GLOBAL_READONLY", detail="管理员全局模型不允许普通用户删除。")
        await self._ensure_config_not_used_by_active_run(config.id)

        await self.session.execute(delete(AiLlmSlotBinding).where(AiLlmSlotBinding.llm_config_id == config.id))
        await self.session.delete(config)
        await self.session.commit()

    async def _ensure_config_not_used_by_active_run(self, config_id: int) -> None:
        """阻止修改或删除仍需暂停恢复的 run 模型配置。"""

        active_run_id = await self.session.scalar(
            select(AiAgentRun.run_id)
            .where(
                AiAgentRun.llm_config_id == config_id,
                AiAgentRun.status.in_(("pending", "running", "paused", "waiting_external", "cancelling")),
            )
            .limit(1)
        )
        if active_run_id is not None:
            raise AppException(
                status_code=409,
                code="AI_LLM_CONFIG_ACTIVE_RUN_IN_USE",
                detail="当前模型仍被运行中的智能体任务使用，请等待任务结束后再修改或删除。",
            )

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
        if config.provider_config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_LLM_PROVIDER_CONFIG_DISABLED", detail="只能绑定供应商可用的大模型配置。")
        self._validate_slot_model_type(slot, config)

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
        if binding.llm_config.provider_config.status != RecordStatus.ACTIVE.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_SLOT_UNBOUND",
                detail="当前智能体槽位绑定的供应商配置不可用，请重新绑定。",
            )
        self._validate_slot_model_type(slot, binding.llm_config)
        await self._apply_current_catalog_capability(binding.llm_config)
        return binding.llm_config

    async def get_selectable_active_config_or_raise(self, config_id: int) -> AiLlmConfig:
        """读取当前用户可作为会话模型选择的启用中配置。"""

        config = await self._get_selectable_config_or_raise(config_id)
        if config.status != RecordStatus.ACTIVE.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_CONFIG_DISABLED",
                detail="只能选择启用中的大模型配置。",
            )
        if config.provider_config.status != RecordStatus.ACTIVE.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_PROVIDER_CONFIG_DISABLED",
                detail="只能选择供应商可用的大模型配置。",
            )
        await self._apply_current_catalog_capability(config)
        return config

    async def _apply_current_catalog_capability(self, config: AiLlmConfig) -> None:
        """新 Run 使用当前目录与用户覆盖合并结果，随后由 Run 快照冻结。"""

        from app.services.ai_chat_config_service import AiChatConfigService

        provider = config.provider_config
        capability, catalog_version = await AiChatConfigService(
            self.session,
            user_id=self.user_id,
            user_role=self.user_role,
        )._resolve_capability(provider, config.model_id, dict(getattr(config, "capability_override_json", {}) or {}))
        config.model_capability_json = AiChatConfigService._legacy_capability_snapshot(provider, config.model_id, capability)
        config.context_window_tokens = int(capability["input_tokens"])
        config.supports_image_input = bool(capability["supports_image_input"])
        config.catalog_version = catalog_version

    def apply_run_reasoning_policy(self, config: AiLlmConfig, *, slot: str, reasoning: ReasoningPolicy) -> None:
        """按本轮所选模型与固定协议校验推理策略，并仅附着到本次 ORM 对象。"""

        from app.services.ai_chat_config_service import AiChatConfigService

        capability = dict(config.model_capability_json or {})
        protocol_key = str(getattr(config.provider_config, "protocol_key", "") or "")
        AiChatConfigService(
            self.session,
            user_id=self.user_id,
            user_role=self.user_role,
        )._validate_policy(slot, protocol_key, capability, reasoning)
        config.reasoning_mode = (
            AiReasoningMode.DISABLED.value if reasoning.mode == "disabled"
            else AiReasoningMode.ENABLED.value if reasoning.mode in {"effort", "budget_tokens"}
            else AiReasoningMode.AUTO.value
        )
        config.reasoning_level = str(reasoning.value) if reasoning.mode == "effort" else None
        config._reasoning_budget_tokens = int(reasoning.value) if reasoning.mode == "budget_tokens" else None
        config._usage_policy_json = {"reasoning": reasoning.model_dump(mode="json")}

    def build_session_llm_metadata(
        self,
        config: AiLlmConfig,
        *,
        selection_kind: Literal["explicit_config", "slot_binding", "run_override"],
    ) -> dict[str, Any]:
        """把模型身份固化为会话 metadata 中的精简只读快照。"""

        provider_config = config.provider_config
        return {
            "selection_kind": selection_kind,
            "config_id": config.id,
            "scope": config.scope,
            "name": config.name,
            "provider_config_id": provider_config.id,
            "provider_config_name": provider_config.name,
            "provider_key": provider_config.provider_key,
            "provider_label": self._provider_label(provider_config),
            "model_id": config.model_id,
            "model_type": config.model_type,
            "supports_image_input": bool(config.supports_image_input),
        }

    def build_run_llm_snapshot(
        self,
        config: AiLlmConfig,
        *,
        selection_kind: Literal["explicit_config", "slot_binding", "run_override"],
    ) -> dict[str, Any]:
        """构建包含可变运行参数且不含供应商密钥的 run 快照。"""

        run_budget = self._derive_config_run_budget(config)
        return {
            **self.build_session_llm_metadata(config, selection_kind=selection_kind),
            "reasoning_mode": config.reasoning_mode,
            "reasoning_level": config.reasoning_level,
            "thinking_enabled": config.reasoning_mode == AiReasoningMode.ENABLED.value,
            "thinking_effort": config.reasoning_level,
            "context_window_tokens": config.context_window_tokens,
            "budget_policy_version": run_budget.budget_policy_version,
            "required_model_context_tokens": run_budget.required_model_context_tokens,
            "request_output_tokens": run_budget.max_output_tokens,
            "runtime_headroom_tokens": run_budget.runtime_headroom_tokens,
            "compression_trigger_tokens": run_budget.compression_trigger_tokens,
            "compression_target_tokens": run_budget.compression_target_tokens,
            # 兼容一个发布周期的历史快照键。
            "model_max_output_tokens": self._snapshot_model_output_limit(config),
            "request_max_output_tokens": run_budget.max_output_tokens,
            "max_output_tokens": run_budget.max_output_tokens,
            "history_token_ratio": 1.0,
            "compression_target_ratio": run_budget.compression_target_ratio,
            "advanced_config_json": dict(config.advanced_config_json or {}),
            "model_capability_json": dict(config.model_capability_json or {}),
            "usage_policy_json": dict(getattr(config, "_usage_policy_json", {}) or {}),
            "reasoning_budget_tokens": getattr(config, "_reasoning_budget_tokens", None),
            "protocol_key": str(getattr(config.provider_config, "protocol_key", "") or ""),
            "catalog_version": getattr(config, "catalog_version", None),
            "base_url_configured": bool(config.provider_config.base_url),
        }

    async def get_slot_binding_lookup(self) -> dict[str, LlmSlotBindingItem]:
        """按槽位返回当前用户全部绑定状态，便于复用到 Agent 列表接口。"""

        personal_bindings = (await self.session.scalars(
            select(AiLlmSlotBinding)
            .where(
                AiLlmSlotBinding.scope == AiLlmConfigScope.PERSONAL.value,
                AiLlmSlotBinding.user_id == self.user_id,
            )
            .options(selectinload(AiLlmSlotBinding.llm_config).selectinload(AiLlmConfig.provider_config))
        )).all()
        global_bindings = (await self.session.scalars(
            select(AiLlmSlotBinding)
            .where(
                AiLlmSlotBinding.scope == AiLlmConfigScope.GLOBAL.value,
                AiLlmSlotBinding.user_id.is_(None),
            )
            .options(selectinload(AiLlmSlotBinding.llm_config).selectinload(AiLlmConfig.provider_config))
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
        provider_config = config.provider_config if config is not None else None
        provider_label = self._provider_label(provider_config) if provider_config is not None else None
        binding_ready = bool(
            config is not None
            and config.status == RecordStatus.ACTIVE.value
            and provider_config is not None
            and provider_config.status == RecordStatus.ACTIVE.value
        )
        if binding_ready:
            try:
                self._validate_slot_model_type(binding.slot, config)
            except AppException:
                binding_ready = False
        result[binding.slot] = LlmSlotBindingItem(
            slot=binding.slot,
            slot_label=definition.label,
            llm_config_id=config.id if config is not None else None,
            llm_config_name=config.name if config is not None else None,
            provider_config_id=provider_config.id if provider_config is not None else None,
            provider_config_name=provider_config.name if provider_config is not None else None,
            provider_key=provider_config.provider_key if provider_config is not None else None,
            provider_label=provider_label,
            model_id=config.model_id if config is not None else None,
            model_type=AiModelType(config.model_type) if config is not None else None,
            binding_ready=binding_ready,
            supports_image_input=bool(config.supports_image_input) if binding_ready and config is not None else False,
            inherited_from_global=inherited_from_global,
        )

    async def _get_provider_config_or_raise(self, provider_config_id: int) -> AiLlmProviderConfig:
        """按主键读取当前用户可见的供应商配置。"""

        statement = select(AiLlmProviderConfig).where(AiLlmProviderConfig.id == provider_config_id)
        config = await self.session.scalar(statement)
        if config is None or not self._can_read_provider_config(config):
            raise AppException(status_code=404, code="AI_LLM_PROVIDER_CONFIG_NOT_FOUND", detail="供应商配置不存在。")
        return config

    async def _get_selectable_provider_config_or_raise(
        self,
        provider_config_id: int,
        *,
        scope: AiLlmConfigScope,
        require_active: bool,
    ) -> AiLlmProviderConfig:
        """读取当前模型可引用的供应商配置，并校验 scope 与状态。"""

        config = await self._get_provider_config_or_raise(provider_config_id)
        if config.scope != scope.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_PROVIDER_SCOPE_MISMATCH",
                detail="模型只能引用同范围的供应商配置。",
            )
        if require_active and config.status != RecordStatus.ACTIVE.value:
            raise AppException(
                status_code=409,
                code="AI_LLM_PROVIDER_CONFIG_DISABLED",
                detail="只能引用启用中的供应商配置。",
            )
        return config

    async def _get_config_or_raise(self, config_id: int) -> AiLlmConfig:
        """按主键读取当前用户可管理的大模型配置。"""

        statement = (
            select(AiLlmConfig)
            .where(AiLlmConfig.id == config_id)
            .options(selectinload(AiLlmConfig.provider_config))
        )
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
            .options(selectinload(AiLlmSlotBinding.llm_config).selectinload(AiLlmConfig.provider_config))
        )
        return await self.session.scalar(statement)

    def _to_config_item(self, config: AiLlmConfig) -> LlmConfigItem:
        """把 ORM 模型转换为前端可消费的模型详情。"""

        provider_config = config.provider_config
        provider_entry = get_llm_provider_entry(provider_config.provider_key)
        run_budget = self._derive_config_run_budget(config)
        capability = capability_from_snapshot(config.model_capability_json or {}) or resolve_model_capability(
            provider_config.provider_key,
            config.model_id,
            default_context_window_tokens=provider_entry.default_context_window_tokens,
            default_model_max_output_tokens=provider_entry.default_max_output_tokens,
            default_supports_image_input=provider_entry.default_supports_image_input,
        )
        effective_reasoning = capability.effective_reasoning(config.reasoning_mode, config.reasoning_level)
        editable = self._can_edit_config(config)
        return LlmConfigItem(
            id=config.id,
            scope=AiLlmConfigScope(config.scope),
            owner_user_id=config.user_id,
            editable=editable,
            name=config.name,
            provider_config_id=provider_config.id,
            provider_config_name=provider_config.name,
            provider_key=provider_config.provider_key,
            provider_label=provider_entry.label,
            model_id=config.model_id,
            model_type=AiModelType(config.model_type),
            reasoning_mode=config.reasoning_mode,
            reasoning_level=config.reasoning_level,
            thinking_enabled=bool(config.reasoning_mode == AiReasoningMode.ENABLED.value and provider_entry.supports_thinking),
            thinking_effort=config.reasoning_level,
            supports_image_input=bool(config.supports_image_input),
            context_window_tokens=int(config.context_window_tokens or LLM_CONTEXT_WINDOW_TOKEN_DEFAULT),
            required_model_context_tokens=run_budget.required_model_context_tokens,
            request_output_tokens=run_budget.max_output_tokens,
            runtime_headroom_tokens=run_budget.runtime_headroom_tokens,
            compression_trigger_tokens=run_budget.compression_trigger_tokens,
            compression_target_tokens=run_budget.compression_target_tokens,
            budget_policy_version=run_budget.budget_policy_version,
            model_max_output_tokens=capability.profile.model_max_output_tokens,
            request_max_output_tokens=run_budget.max_output_tokens,
            max_output_tokens=run_budget.max_output_tokens,
            capability_source=capability.profile.source,
            capability_verified=capability.profile.verified,
            model_capability_json={**capability.as_dict(), "provider_key": provider_config.provider_key},
            effective_reasoning=effective_reasoning,
            history_token_ratio=1.0,
            compression_target_ratio=run_budget.compression_target_ratio,
            advanced_config_json=self._sanitize_stored_advanced_config(config.advanced_config_json or {}),
            status=config.status,
            created_at=config.created_at.isoformat() if config.created_at is not None else None,
            updated_at=config.updated_at.isoformat() if config.updated_at is not None else None,
        )

    @staticmethod
    def _derive_config_run_budget(config: AiLlmConfig) -> ModelRunBudget:
        """按平台可用输入窗口和能力档案硬限制返回固定运行预算。"""

        provider_key = config.provider_config.provider_key
        capability = capability_from_snapshot(config.model_capability_json or {})
        model_output_limit = capability.profile.model_max_output_tokens if capability is not None else 65_536
        return derive_model_run_budget(
            int(config.context_window_tokens or LLM_CONTEXT_WINDOW_TOKEN_DEFAULT),
            provider_output_limit=AiLlmService._model_output_limit(
                model_output_limit,
                provider_key,
            ),
        )

    @staticmethod
    def _snapshot_model_output_limit(config: AiLlmConfig) -> int:
        """从配置能力快照读取模型输出硬上限，仅用于旧快照字段兼容。"""

        capability = capability_from_snapshot(config.model_capability_json or {})
        return capability.profile.model_max_output_tokens if capability is not None else 65_536

    @staticmethod
    def _recommended_usable_input_tokens(capability, provider_key: str) -> int:
        """返回模型表单建议的可用输入窗口；未知模型保持 200K 的保守建议值。"""

        if capability.profile.source == "provider_default":
            return 200_000
        output_limit = AiLlmService._model_output_limit(capability.profile.model_max_output_tokens, provider_key)
        output_tokens = derive_model_run_budget(LLM_CONTEXT_WINDOW_TOKEN_DEFAULT, provider_output_limit=output_limit).max_output_tokens
        return max(LLM_CONTEXT_WINDOW_TOKEN_MIN, capability.profile.context_window_tokens - output_tokens)

    @staticmethod
    def _validate_model_context_capacity(capability, budget: ModelRunBudget) -> None:
        """已验证模型必须能够容纳用户输入窗口与实际输出预算。"""

        if capability.profile.source == "provider_default":
            return
        if budget.required_model_context_tokens <= capability.profile.context_window_tokens:
            return
        raise AppException(
            status_code=400,
            code="AI_LLM_CONTEXT_WINDOW_UNSUPPORTED",
            detail=(
                f"当前配置至少需要模型支持 {budget.required_model_context_tokens} tokens 总上下文，"
                f"但能力档案仅声明 {capability.profile.context_window_tokens} tokens。"
            ),
        )

    @classmethod
    def _sanitize_stored_advanced_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        """读取历史配置时剔除旧 max_tokens，避免受管预算字段阻塞模型列表。"""

        sanitized = {key: item for key, item in value.items() if key != "max_tokens"}
        return cls._validate_advanced_config(sanitized)

    @staticmethod
    def _validate_slot_model_type(slot: str, config: AiLlmConfig) -> None:
        """校验视觉槽位与模型协议能力，普通智能体槽位只能使用聊天模型。"""

        if slot == AiLlmSlot.IMAGE_UNDERSTANDING.value:
            if config.model_type != AiModelType.CHAT.value or not bool(config.supports_image_input):
                raise AppException(status_code=409, code="AI_LLM_SLOT_MODEL_INCOMPATIBLE", detail="图片理解槽位必须绑定支持图片输入的聊天模型。")
            return
        if slot == AiLlmSlot.IMAGE_GENERATION.value:
            if config.model_type != AiModelType.IMAGE_GENERATION.value:
                raise AppException(status_code=409, code="AI_LLM_SLOT_MODEL_INCOMPATIBLE", detail="图片生成槽位必须绑定图片生成模型。")
            return
        if config.model_type != AiModelType.CHAT.value:
            raise AppException(status_code=409, code="AI_LLM_SLOT_MODEL_INCOMPATIBLE", detail="智能体槽位只能绑定聊天模型。")

    def _to_provider_config_item(self, config: AiLlmProviderConfig) -> LlmProviderConfigItem:
        """把供应商配置 ORM 模型转换为前端可消费的详情。"""

        provider_entry = get_llm_provider_entry(config.provider_key)
        raw_api_key = self._cipher.decrypt(config.api_key_ciphertext)
        editable = self._can_edit_provider_config(config)
        return LlmProviderConfigItem(
            id=config.id,
            scope=AiLlmConfigScope(config.scope),
            owner_user_id=config.user_id,
            editable=editable,
            name=config.name,
            provider_key=config.provider_key,
            provider_label=provider_entry.label,
            provider_type=AiModelType(provider_entry.provider_type),
            base_url=config.base_url,
            status=config.status,
            has_api_key=bool(raw_api_key),
            api_key_masked=self._cipher.mask(raw_api_key) if editable or config.scope == AiLlmConfigScope.GLOBAL.value else None,
            created_at=config.created_at.isoformat() if config.created_at is not None else None,
            updated_at=config.updated_at.isoformat() if config.updated_at is not None else None,
        )

    @staticmethod
    def _provider_label(config: AiLlmProviderConfig) -> str:
        """目录供应商不在旧静态表时使用用户连接名称，避免运行链路依赖静态 key 覆盖率。"""

        try:
            return get_llm_provider_entry(config.provider_key).label
        except AppException:
            return config.name

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

    def _can_read_provider_config(self, config: AiLlmProviderConfig) -> bool:
        """判断当前用户是否可读取供应商配置。"""

        if config.scope == AiLlmConfigScope.GLOBAL.value:
            return True
        return config.user_id == self.user_id

    def _can_edit_provider_config(self, config: AiLlmProviderConfig) -> bool:
        """判断当前用户是否可编辑供应商配置。"""

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

    @staticmethod
    def _model_output_limit(model_max_output_tokens: int, provider_key: str) -> int:
        """合并模型硬上限与供应商额外硬限制。"""

        return min(model_max_output_tokens, MIMO_MAX_COMPLETION_TOKENS) if provider_key == "mimo" else model_max_output_tokens

    @staticmethod
    def _validate_reasoning_policy(capability, mode: str) -> None:
        """拒绝模型不支持的推理模式，避免延迟到真实请求才失败。"""

        if mode == AiReasoningMode.ENABLED.value and not capability.profile.supports_reasoning:
            raise AppException(status_code=400, code="AI_LLM_REASONING_UNSUPPORTED", detail="当前模型能力档案不支持推理。")
        if mode == AiReasoningMode.DISABLED.value and not capability.profile.supports_explicit_disable:
            raise AppException(status_code=400, code="AI_LLM_REASONING_DISABLE_UNSUPPORTED", detail="当前模型不能确认支持显式关闭推理，请改用自动模式。")

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
        if entry.requires_base_url and not base_url:
            raise AppException(
                status_code=400,
                code="AI_LLM_BASE_URL_REQUIRED",
                detail="当前供应商必须配置 Base URL。",
            )
        if entry.provider_type == AiModelType.IMAGE_GENERATION.value:
            validate_image_provider_connection(provider_key, base_url)
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
    def _validate_provider_model_type(provider_entry, model_type: str) -> None:
        """校验供应商目录是否声明支持目标模型类型。"""

        if model_type != str(provider_entry.provider_type):
            raise AppException(
                status_code=400,
                code="AI_LLM_PROVIDER_MODEL_TYPE_MISMATCH",
                detail="当前供应商类型与所选模型类型不匹配。",
            )

    @staticmethod
    def _reject_e2e_mock_model_outside_e2e_database(model_id: str) -> None:
        """禁止在非 E2E 数据库通过正常业务 API 创建或选择 e2e-mock-* 模型。"""

        from app.ai.testing.scenarios import E2E_MOCK_MODEL_PREFIXES
        from app.core.testing_environment import require_e2e_database

        normalized = str(model_id or "").strip()
        if not any(normalized.startswith(prefix) for prefix in E2E_MOCK_MODEL_PREFIXES):
            return
        require_e2e_database()

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
        managed_keys = {
            "reasoning",
            "openai_reasoning_effort",
            "openrouter_reasoning",
            "google_thinking_config",
            "enable_thinking",
            "thinking_budget",
            "think",
            "thinking",
            "max_tokens",
            "max_output_tokens",
            "request_max_output_tokens",
            "request_output_tokens",
            "model_max_output_tokens",
            "context_window_tokens",
            "runtime_headroom_tokens",
            "compression_trigger_tokens",
            "compression_target_tokens",
            "compression_target_ratio",
        }
        nested_conflicts = AiLlmService._find_nested_keys(value, managed_keys)
        if nested_conflicts:
            raise AppException(
                status_code=400,
                code="AI_LLM_ADVANCED_CONFIG_CONFLICT",
                detail=f"高级配置禁止覆盖受管字段：{', '.join(nested_conflicts)}。",
            )
        return dict(value)

    @staticmethod
    def _find_nested_keys(value: Any, managed_keys: set[str], path: str = "") -> list[str]:
        """递归查找受管推理与预算键，覆盖对象、数组和 extra_body 深层结构。"""

        conflicts: list[str] = []
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key).lower() in managed_keys:
                    conflicts.append(child_path)
                conflicts.extend(AiLlmService._find_nested_keys(child, managed_keys, child_path))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                conflicts.extend(AiLlmService._find_nested_keys(child, managed_keys, f"{path}[{index}]"))
        return sorted(set(conflicts))

    @classmethod
    def _validate_model_advanced_config(
        cls,
        *,
        provider_key: str,
        model_id: str,
        model_type: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        """聊天模型沿用公共保护规则，生图模型按注册能力白名单校验。"""

        normalized = cls._validate_advanced_config(value)
        if model_type != AiModelType.IMAGE_GENERATION.value:
            return normalized
        model = get_image_model_spec(provider_key, model_id)
        return validate_advanced_options(model, normalized)
