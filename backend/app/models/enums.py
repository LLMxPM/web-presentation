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
    COMPONENT_MANAGER = "component_manager"
    RESOURCE_MANAGER = "resource_manager"


class AiLlmConfigScope(str, Enum):
    """大模型配置归属范围。"""

    GLOBAL = "global"
    PERSONAL = "personal"


class AiThinkingMode(str, Enum):
    """不同供应商启用思考模式时的参数映射策略。"""

    NONE = "none"
    OPENAI_REASONING = "openai_reasoning"
    OPENAI_EXTRA_BODY_THINKING = "openai_extra_body_thinking"
    DASHSCOPE_ENABLE_THINKING = "dashscope_enable_thinking"
    OLLAMA_THINK = "ollama_think"
    GOOGLE_THINKING_LEVEL = "google_thinking_level"
