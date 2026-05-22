"""文件功能：封装用户级智能体提示词、工具开关与工具提示词配置逻辑。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent_catalog import (
    AgentCatalogEntry,
    AgentToolCatalogEntry,
    get_agent_catalog_entry,
    get_agent_tool_catalog_entry,
    list_agent_catalog_entries,
)
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, EffectiveToolRuntimeConfig
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    COMPONENT_MANAGER_AGENT_ID,
    RESOURCE_MANAGER_AGENT_ID,
    apply_tool_spec_metadata,
    build_agent_tools_from_group_specs,
    get_agent_group_spec,
    get_agent_tool_spec,
    list_runtime_disclosure_groups,
    resolve_required_context_fields,
)
from app.ai.tools.disclosure import get_tool_group_definitions
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.ai_agent_config import AiAgentToolUserConfig, AiAgentUserConfig
from app.schemas.agent_config import (
    AgentCatalogItem,
    AgentConfigItem,
    AgentConfigUpdateRequest,
    AgentTeamMemberConfigItem,
    AgentToolConfigItem,
    AgentToolConfigUpdateRequest,
    AgentToolGuideItem,
    AgentToolGroupConfigItem,
)


@dataclass(slots=True, frozen=True)
class AgentConfigSummary:
    """Agent 列表接口所需的轻量配置摘要，避免构建完整工具调用说明。"""

    prompt_customized: bool
    enabled_tool_count: int
    disabled_tool_count: int


class AiAgentConfigService:
    """统一管理当前用户的智能体提示词和工具覆盖配置。"""

    def __init__(self, session: AsyncSession, *, user_id: int) -> None:
        self.session = session
        self.user_id = user_id

    async def list_agent_catalog(self) -> list[AgentCatalogItem]:
        """返回系统内置智能体目录，不叠加用户覆盖。"""

        return [
            self._build_catalog_item(catalog, build_runtime_config=False)
            for catalog in list_agent_catalog_entries()
        ]

    async def list_configs(self) -> list[AgentConfigItem]:
        """返回当前用户的全部智能体有效配置。"""

        return [
            await self.get_config(catalog.id)
            for catalog in list_agent_catalog_entries()
        ]

    async def get_config(self, agent_id: str) -> AgentConfigItem:
        """读取某个智能体的当前用户有效配置。"""

        catalog = self._get_catalog_or_raise(agent_id)
        runtime_config = await self.get_effective_runtime_config(agent_id)
        team_members = await self._build_team_members_for_config(catalog)
        return self._build_config_item(catalog, runtime_config, team_members=team_members)

    async def get_config_summary(self, agent_id: str) -> AgentConfigSummary:
        """读取 Agent 列表接口所需的轻量配置摘要。"""

        runtime_config = await self.get_effective_runtime_config(agent_id)
        return AgentConfigSummary(
            prompt_customized=runtime_config.prompt_customized,
            enabled_tool_count=len(runtime_config.enabled_tool_keys),
            disabled_tool_count=len(runtime_config.disabled_tool_keys),
        )

    async def get_effective_runtime_config(self, agent_id: str) -> EffectiveAgentRuntimeConfig:
        """合成某个智能体在当前用户下的运行时配置。"""

        catalog = self._get_catalog_or_raise(agent_id)
        agent_config = await self._get_agent_config_model(agent_id)
        tool_configs = await self._get_tool_config_models(agent_id)
        tool_config_map = {item.tool_key: item for item in tool_configs}

        effective_tools: dict[str, EffectiveToolRuntimeConfig] = {}
        for tool in catalog.tools:
            override = tool_config_map.get(tool.key)
            effective_tools[tool.key] = EffectiveToolRuntimeConfig(
                key=tool.key,
                enabled=True if not tool.configurable else (override.enabled if override is not None else True),
                configurable=tool.configurable,
                description_override=override.description_override if override is not None else None,
                instructions_override=override.instructions_override if override is not None else None,
            )

        return EffectiveAgentRuntimeConfig(
            agent_id=agent_id,
            description_override=agent_config.description_override if agent_config is not None else None,
            prompt_override=agent_config.prompt_override if agent_config is not None else None,
            tool_configs=effective_tools,
        )

    async def update_agent_config(
        self,
        agent_id: str,
        payload: AgentConfigUpdateRequest,
        *,
        operator_id: int,
    ) -> AgentConfigItem:
        """更新某个 Agent 的用户描述或业务补充提示词。"""

        self._get_catalog_or_raise(agent_id)
        config = await self._get_agent_config_model(agent_id)
        if payload.restore_default:
            if config is not None:
                await self.session.delete(config)
                await self.session.commit()
            return await self.get_config(agent_id)

        if "prompt_override" not in payload.model_fields_set and "description_override" not in payload.model_fields_set:
            return await self.get_config(agent_id)

        next_prompt = config.prompt_override if config is not None else None
        next_description = config.description_override if config is not None else None
        if "prompt_override" in payload.model_fields_set:
            next_prompt = self._normalize_optional_text(payload.prompt_override)
        if "description_override" in payload.model_fields_set:
            next_description = self._normalize_optional_text(payload.description_override)

        if next_prompt is None and next_description is None:
            if config is not None:
                await self.session.delete(config)
                await self.session.commit()
            return await self.get_config(agent_id)

        if config is None:
            config = AiAgentUserConfig(
                user_id=self.user_id,
                agent_id=agent_id,
                description_override=next_description,
                prompt_override=next_prompt,
                prompt_mode="override",
                created_by=operator_id,
                updated_by=operator_id,
            )
            self.session.add(config)
        else:
            config.description_override = next_description
            config.prompt_override = next_prompt
            config.updated_by = operator_id

        await self.session.commit()
        return await self.get_config(agent_id)

    async def update_tool_config(
        self,
        agent_id: str,
        tool_key: str,
        payload: AgentToolConfigUpdateRequest,
        *,
        operator_id: int,
    ) -> AgentConfigItem:
        """更新某个 Agent 内单个工具的用户覆盖配置。"""

        self._get_catalog_or_raise(agent_id)
        tool_catalog = get_agent_tool_catalog_entry(agent_id, tool_key)
        if tool_catalog is None:
            raise AppException(status_code=404, code="AI_AGENT_TOOL_NOT_FOUND", detail="指定智能体工具不存在。")

        config = await self._get_tool_config_model(agent_id, tool_key)
        if payload.restore_default:
            if config is not None:
                await self.session.delete(config)
                await self.session.commit()
            return await self.get_config(agent_id)

        if not tool_catalog.configurable:
            if payload.enabled is False or self._normalize_optional_text(payload.description_override) or self._normalize_optional_text(payload.instructions_override):
                raise AppException(
                    status_code=409,
                    code="AI_AGENT_TOOL_NOT_CONFIGURABLE",
                    detail="系统引导工具不允许用户关闭或覆盖提示词。",
                )
            return await self.get_config(agent_id)

        next_enabled = payload.enabled if payload.enabled is not None else (config.enabled if config is not None else True)
        next_description = (
            self._normalize_optional_text(payload.description_override)
            if "description_override" in payload.model_fields_set
            else (config.description_override if config is not None else None)
        )
        next_instructions = (
            self._normalize_optional_text(payload.instructions_override)
            if "instructions_override" in payload.model_fields_set
            else (config.instructions_override if config is not None else None)
        )

        if next_enabled is True and next_description is None and next_instructions is None:
            if config is not None:
                await self.session.delete(config)
                await self.session.commit()
            return await self.get_config(agent_id)

        if config is None:
            config = AiAgentToolUserConfig(
                user_id=self.user_id,
                agent_id=agent_id,
                tool_key=tool_key,
                enabled=next_enabled,
                description_override=next_description,
                instructions_override=next_instructions,
                created_by=operator_id,
                updated_by=operator_id,
            )
            self.session.add(config)
        else:
            config.enabled = next_enabled
            config.description_override = next_description
            config.instructions_override = next_instructions
            config.updated_by = operator_id

        await self.session.commit()
        return await self.get_config(agent_id)

    async def delete_user_configs(self, *, user_id: int) -> None:
        """删除某个用户全部智能体配置，供后续账号删除或测试复用。"""

        await self.session.execute(delete(AiAgentToolUserConfig).where(AiAgentToolUserConfig.user_id == user_id))
        await self.session.execute(delete(AiAgentUserConfig).where(AiAgentUserConfig.user_id == user_id))
        await self.session.commit()

    async def _get_agent_config_model(self, agent_id: str) -> AiAgentUserConfig | None:
        """读取当前用户某个 Agent 的描述与业务补充提示词模型。"""

        statement = select(AiAgentUserConfig).where(
            AiAgentUserConfig.user_id == self.user_id,
            AiAgentUserConfig.agent_id == agent_id,
        )
        return await self.session.scalar(statement)

    async def _get_tool_config_model(self, agent_id: str, tool_key: str) -> AiAgentToolUserConfig | None:
        """读取当前用户某个 Agent 工具的覆盖模型。"""

        statement = select(AiAgentToolUserConfig).where(
            AiAgentToolUserConfig.user_id == self.user_id,
            AiAgentToolUserConfig.agent_id == agent_id,
            AiAgentToolUserConfig.tool_key == tool_key,
        )
        return await self.session.scalar(statement)

    async def _get_tool_config_models(self, agent_id: str) -> list[AiAgentToolUserConfig]:
        """读取当前用户某个 Agent 的全部工具覆盖模型。"""

        statement = select(AiAgentToolUserConfig).where(
            AiAgentToolUserConfig.user_id == self.user_id,
            AiAgentToolUserConfig.agent_id == agent_id,
        )
        return list((await self.session.scalars(statement)).all())

    def _build_catalog_item(self, catalog: AgentCatalogEntry, *, build_runtime_config: bool) -> AgentCatalogItem:
        """把内置目录转换成响应模型。"""

        runtime_config = None
        if build_runtime_config:
            runtime_config = EffectiveAgentRuntimeConfig(
                agent_id=catalog.id,
                prompt_override=None,
                description_override=None,
                tool_configs={
                    tool.key: EffectiveToolRuntimeConfig(
                        key=tool.key,
                        enabled=True,
                        configurable=tool.configurable,
                    )
                    for tool in catalog.tools
                },
            )
        runtime_tool_map = self._build_runtime_tool_map(catalog.id)
        return AgentCatalogItem(
            id=catalog.id,
            name=catalog.name,
            icon=catalog.icon,
            summary=catalog.summary,
            default_session_name=catalog.default_session_name,
            capabilities=list(catalog.capabilities),
            scope_type=catalog.scope_type,
            entry_kind=catalog.entry_kind,
            llm_slot=catalog.llm_slot,
            default_description=catalog.description,
            description=catalog.description,
            description_override=None,
            description_customized=False,
            role=catalog.role,
            system_prompt=catalog.system_prompt,
            default_prompt=catalog.default_prompt,
            team_members=self._build_default_team_members(catalog),
            tool_groups=self._build_tool_groups(
                catalog,
                runtime_config,
                runtime_tool_map=runtime_tool_map,
            ),
        )

    def _build_config_item(
        self,
        catalog: AgentCatalogEntry,
        runtime_config: EffectiveAgentRuntimeConfig,
        *,
        team_members: list[AgentTeamMemberConfigItem],
    ) -> AgentConfigItem:
        """把有效配置转换成响应模型。"""

        disabled_count = len(runtime_config.disabled_tool_keys)
        enabled_count = len(runtime_config.enabled_tool_keys)
        runtime_tool_map = self._build_runtime_tool_map(catalog.id)
        description = runtime_config.description_override or catalog.description
        return AgentConfigItem(
            id=catalog.id,
            name=catalog.name,
            icon=catalog.icon,
            summary=catalog.summary,
            default_session_name=catalog.default_session_name,
            capabilities=list(catalog.capabilities),
            scope_type=catalog.scope_type,
            entry_kind=catalog.entry_kind,
            llm_slot=catalog.llm_slot,
            default_description=catalog.description,
            description=description,
            description_override=runtime_config.description_override,
            description_customized=runtime_config.description_customized,
            role=catalog.role,
            system_prompt=catalog.system_prompt,
            default_prompt=catalog.default_prompt,
            prompt_override=runtime_config.prompt_override,
            effective_prompt=runtime_config.prompt_override or catalog.default_prompt,
            prompt_customized=runtime_config.prompt_customized,
            enabled_tool_count=enabled_count,
            disabled_tool_count=disabled_count,
            team_members=team_members,
            tool_groups=self._build_tool_groups(
                catalog,
                runtime_config,
                runtime_tool_map=runtime_tool_map,
            ),
        )

    async def _build_team_members_for_config(self, catalog: AgentCatalogEntry) -> list[AgentTeamMemberConfigItem]:
        """为内容助手配置生成 Team 成员描述配置。"""

        if catalog.id != AGENT_COORDINATOR_AGENT_ID:
            return []

        result: list[AgentTeamMemberConfigItem] = []
        for member_agent_id in (COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
            member_catalog = self._get_catalog_or_raise(member_agent_id)
            member_runtime_config = await self.get_effective_runtime_config(member_agent_id)
            result.append(self._build_team_member_item(member_catalog, member_runtime_config))
        return result

    @staticmethod
    def _build_default_team_members(catalog: AgentCatalogEntry) -> list[AgentTeamMemberConfigItem]:
        """为内置目录生成未叠加用户覆盖的 Team 成员描述。"""

        if catalog.id != AGENT_COORDINATOR_AGENT_ID:
            return []
        result: list[AgentTeamMemberConfigItem] = []
        for member_agent_id in (COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID):
            member_catalog = get_agent_catalog_entry(member_agent_id)
            if member_catalog is None:
                continue
            result.append(
                AgentTeamMemberConfigItem(
                    id=member_catalog.id,
                    name=member_catalog.name,
                    icon=member_catalog.icon,
                    default_description=member_catalog.description,
                    description=member_catalog.description,
                    description_override=None,
                    description_customized=False,
                )
            )
        return result

    @staticmethod
    def _build_team_member_item(
        catalog: AgentCatalogEntry,
        runtime_config: EffectiveAgentRuntimeConfig,
    ) -> AgentTeamMemberConfigItem:
        """把成员 Agent 目录与用户描述覆盖折叠为 Team 成员配置项。"""

        description = runtime_config.description_override or catalog.description
        return AgentTeamMemberConfigItem(
            id=catalog.id,
            name=catalog.name,
            icon=catalog.icon,
            default_description=catalog.description,
            description=description,
            description_override=runtime_config.description_override,
            description_customized=runtime_config.description_customized,
        )

    def _build_tool_groups(
        self,
        catalog: AgentCatalogEntry,
        runtime_config: EffectiveAgentRuntimeConfig | None,
        *,
        runtime_tool_map: dict[str, object],
    ) -> list[AgentToolGroupConfigItem]:
        """按目录顺序把工具折叠为工具组响应。"""

        grouped: OrderedDict[str, AgentToolGroupConfigItem] = OrderedDict()
        for tool in catalog.tools:
            group = grouped.setdefault(
                tool.group_key,
                AgentToolGroupConfigItem(
                    key=tool.group_key,
                    label=tool.group_label,
                    description=self._resolve_group_description(catalog.id, tool.group_key),
                    tools=[],
                ),
            )
            group.tools.append(
                self._build_tool_item(
                    catalog.id,
                    tool,
                    runtime_config,
                    runtime_tool_map=runtime_tool_map,
                )
            )
        return list(grouped.values())

    def _build_tool_item(
        self,
        agent_id: str,
        tool: AgentToolCatalogEntry,
        runtime_config: EffectiveAgentRuntimeConfig | None,
        *,
        runtime_tool_map: dict[str, object],
    ) -> AgentToolConfigItem:
        """把工具目录与用户覆盖折叠为响应项。"""

        config = runtime_config.tool_configs.get(tool.key) if runtime_config is not None else None
        description_override = config.description_override if config is not None else None
        instructions_override = config.instructions_override if config is not None else None
        return AgentToolConfigItem(
            key=tool.key,
            label=tool.label,
            group_key=tool.group_key,
            group_label=tool.group_label,
            default_description=tool.description,
            description=description_override or tool.description,
            description_override=description_override,
            default_instructions=tool.default_instructions,
            instructions=instructions_override or tool.default_instructions,
            instructions_override=instructions_override,
            enabled=True if config is None else config.enabled,
            configurable=tool.configurable,
            requires_confirmation=tool.requires_confirmation,
            risk_level=tool.risk_level,
            agent_guide=self._build_agent_tool_guide(
                agent_id=agent_id,
                tool=tool,
                effective_description=description_override or tool.description,
                instructions=instructions_override or tool.default_instructions,
                runtime_tool_map=runtime_tool_map,
            ),
        )

    def _build_agent_tool_guide(
        self,
        *,
        agent_id: str,
        tool: AgentToolCatalogEntry,
        effective_description: str,
        instructions: str | None,
        runtime_tool_map: dict[str, object],
    ) -> AgentToolGuideItem:
        """生成面向 Agent 的只读工具调用说明。"""

        runtime_tool = runtime_tool_map.get(tool.key)
        parameters_schema = getattr(runtime_tool, "parameters", None) if runtime_tool is not None else None
        parameters_schema = parameters_schema if isinstance(parameters_schema, dict) else None
        spec = get_agent_tool_spec(agent_id, tool.key)
        return AgentToolGuideItem(
            tool_name=tool.key,
            effective_description=effective_description,
            system_description=tool.description,
            instructions=instructions,
            parameters_schema=parameters_schema,
            call_example=self._build_call_example(tool.key, parameters_schema),
            response_example=spec.response_example if spec is not None else None,
            response_notes=spec.response_notes if spec is not None else None,
            required_context_fields=list(resolve_required_context_fields(agent_id, tool.key)),
            runtime_disclosure_groups=list(list_runtime_disclosure_groups(agent_id, tool.key)),
            requires_confirmation=tool.requires_confirmation,
            risk_level=tool.risk_level,
        )

    @staticmethod
    def _resolve_group_description(agent_id: str, group_key: str) -> str:
        """从统一工具组规格读取分组说明。"""

        group = get_agent_group_spec(agent_id, group_key)
        return group.description if group is not None else ""

    @staticmethod
    def _build_runtime_tool_map(agent_id: str) -> dict[str, object]:
        """构建指定智能体的实际 Agno 工具索引，用于读取参数 schema。"""

        session_factory = get_session_factory()
        if agent_id == AGENT_COORDINATOR_AGENT_ID:
            tools = []
            for definition in get_tool_group_definitions(session_factory=session_factory).values():
                tools.extend(definition.build_tools())
            tools = apply_tool_spec_metadata(agent_id=agent_id, tools=tools)
        elif agent_id in {COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID}:
            tools = build_agent_tools_from_group_specs(
                agent_id=agent_id,
                session_factory=session_factory,
            )
        else:
            tools = []

        tool_map: dict[str, object] = {}
        for tool_item in tools:
            tool_name = str(getattr(tool_item, "name", "") or "")
            if tool_name and tool_name not in tool_map:
                tool_map[tool_name] = tool_item
        return tool_map

    @classmethod
    def _build_call_example(cls, tool_name: str, parameters_schema: dict[str, object] | None) -> dict[str, object]:
        """根据 Agno 参数 schema 生成最小工具调用示例。"""

        properties = parameters_schema.get("properties", {}) if parameters_schema else {}
        arguments = {
            str(name): cls._sample_schema_value(schema)
            for name, schema in properties.items()
            if isinstance(schema, dict)
        } if isinstance(properties, dict) else {}
        return {
            "tool_name": tool_name,
            "arguments": arguments,
        }

    @classmethod
    def _sample_schema_value(cls, schema: dict[str, object]) -> object:
        """为 JSON Schema 片段生成可读的占位示例值。"""

        if "const" in schema:
            return schema["const"]

        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and enum_values:
            return enum_values[0]

        any_of = schema.get("anyOf")
        if isinstance(any_of, list):
            for option in any_of:
                if isinstance(option, dict) and option.get("type") != "null":
                    return cls._sample_schema_value(option)
            return None

        schema_type = schema.get("type")
        if schema_type == "string":
            return "string"
        if schema_type == "integer":
            return 1
        if schema_type == "number":
            return 1
        if schema_type == "boolean":
            return True
        if schema_type == "array":
            item_schema = schema.get("items")
            return [cls._sample_schema_value(item_schema)] if isinstance(item_schema, dict) else []
        if schema_type == "object":
            properties = schema.get("properties")
            required = schema.get("required")
            if not isinstance(properties, dict) or not isinstance(required, list):
                return {}
            return {
                str(name): cls._sample_schema_value(properties[name])
                for name in required
                if name in properties and isinstance(properties[name], dict)
            }
        return None

    @staticmethod
    def _get_catalog_or_raise(agent_id: str) -> AgentCatalogEntry:
        """读取内置 Agent 目录；不存在时返回标准异常。"""

        catalog = get_agent_catalog_entry(agent_id)
        if catalog is None:
            raise AppException(status_code=404, code="AI_AGENT_NOT_FOUND", detail="指定智能体不存在。")
        return catalog

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """归一化可选文本；空白文本视为未覆盖。"""

        normalized = str(value or "").strip()
        return normalized or None
