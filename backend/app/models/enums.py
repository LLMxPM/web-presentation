"""文件功能：定义后台使用的状态枚举，统一数据库与接口层的取值范围。"""

from enum import Enum


class RecordStatus(str, Enum):
    """业务资源状态，用于控制启用与归档展示。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class UserRole(str, Enum):
    """平台账号角色，用于区分平台治理与普通工作空间用户。"""

    PLATFORM_ADMIN = "platform_admin"
    WORKSPACE_USER = "workspace_user"


class WorkspaceMemberRole(str, Enum):
    """工作空间成员角色，首期仅开放 owner 并为后续协作预留。"""

    OWNER = "owner"
    MEMBER = "member"


class PageFileType(str, Enum):
    """页面文件类型枚举，用于约束页面源码下发时的文件扩展名。"""

    VUE = "vue"
    TS = "ts"
    JS = "js"
    JSON = "json"
    MD = "md"
    TXT = "txt"
    YAML = "yaml"


class WorkspaceComponentType(str, Enum):
    """工作空间组件固定分类，用于约束组件库筛选与元数据维护。"""

    PAGE_COMPONENT = "页面组件"
    CONTENT_COMPONENT = "内容组件"
    ATOMIC_COMPONENT = "原子组件"


_COMPONENT_TYPE_ALIAS_MAP: dict[str, WorkspaceComponentType] = {
    "page": WorkspaceComponentType.PAGE_COMPONENT,
    "page_component": WorkspaceComponentType.PAGE_COMPONENT,
    "template": WorkspaceComponentType.PAGE_COMPONENT,
    "页面组件": WorkspaceComponentType.PAGE_COMPONENT,

    "content": WorkspaceComponentType.CONTENT_COMPONENT,
    "content_component": WorkspaceComponentType.CONTENT_COMPONENT,
    "custom": WorkspaceComponentType.CONTENT_COMPONENT,
    "card": WorkspaceComponentType.CONTENT_COMPONENT,
    "section": WorkspaceComponentType.CONTENT_COMPONENT,
    "内容组件": WorkspaceComponentType.CONTENT_COMPONENT,

    "atomic": WorkspaceComponentType.ATOMIC_COMPONENT,
    "atomic_component": WorkspaceComponentType.ATOMIC_COMPONENT,
    "atom": WorkspaceComponentType.ATOMIC_COMPONENT,
    "basic": WorkspaceComponentType.ATOMIC_COMPONENT,
    "原子组件": WorkspaceComponentType.ATOMIC_COMPONENT,
}


def resolve_workspace_component_type(
    value: str | WorkspaceComponentType | None,
) -> WorkspaceComponentType:
    """将外部 API、CLI 或别名传入的组件类型标识归一化为内部 WorkspaceComponentType 枚举。"""

    if value is None:
        return WorkspaceComponentType.CONTENT_COMPONENT
    if isinstance(value, WorkspaceComponentType):
        return value
    normalized = str(value).strip().lower()
    if normalized in _COMPONENT_TYPE_ALIAS_MAP:
        return _COMPONENT_TYPE_ALIAS_MAP[normalized]
    for item in WorkspaceComponentType:
        if item.value == value:
            return item
    raise ValueError(
        f"不支持的组件类型: '{value}'。有效类型包括: content (card/section/custom), page (template), atomic (atom/basic)。"
    )


class PageVersionStorageType(str, Enum):
    """页面版本存储类型，区分完整快照与基于最新链路的向后 diff。"""

    SNAPSHOT = "snapshot"
    DIFF = "diff"


class ProjectRouteType(str, Enum):
    """项目路由节点类型，区分页节点与分组节点。"""

    GROUP = "group"
    PAGE = "page"


class AssetType(str, Enum):
    """资源库静态资源大类枚举。"""

    ICON = "icon"
    FONT = "font"
    IMAGE = "image"
    VIDEO = "video"
    DRAWIO = "drawio"
    MERMAID = "mermaid"
    CHART = "chart"
    FORMULA = "formula"


class AssetRole(str, Enum):
    """资源在平台内的职责分组。"""

    FOUNDATION = "foundation"
    CONTENT = "content"


class AiLlmSlot(str, Enum):
    """智能体可绑定的大模型槽位枚举。"""

    AGENT_COORDINATOR = "agent_coordinator"
    IMAGE_UNDERSTANDING = "image_understanding"
    IMAGE_GENERATION = "image_generation"


class AiModelType(str, Enum):
    """模型配置的运行协议类型。"""

    CHAT = "chat"
    IMAGE_GENERATION = "image_generation"


class AiLlmConfigScope(str, Enum):
    """大模型配置归属范围。"""

    GLOBAL = "global"
    PERSONAL = "personal"


class AiThinkingMode(str, Enum):
    """不同供应商启用思考模式时的参数映射策略。"""

    NONE = "none"
    OPENAI_REASONING = "openai_reasoning"
    OPENROUTER_REASONING = "openrouter_reasoning"
    OPENAI_EXTRA_BODY_THINKING = "openai_extra_body_thinking"
    DASHSCOPE_ENABLE_THINKING = "dashscope_enable_thinking"
    OLLAMA_THINK = "ollama_think"
    GOOGLE_THINKING_LEVEL = "google_thinking_level"


class AiReasoningMode(str, Enum):
    """平台统一的推理启停语义。"""

    AUTO = "auto"
    DISABLED = "disabled"
    ENABLED = "enabled"


class AiReasoningLevel(str, Enum):
    """平台面向用户暴露的四档推理强度。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"
