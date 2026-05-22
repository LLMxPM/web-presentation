"""文件功能：定义项目路由树的结构化请求与响应模型，供后台接口、预览与编辑器共用。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import SchemaBase


class ProjectRoutePageBinding(SchemaBase):
    """页面被项目路由引用时的路径绑定摘要。"""

    route_id: int
    parent_route: str | None = None
    route: str
    full_path: str
    parent_order: int | None = None
    order: int


class ProjectRouteChildWrite(BaseModel):
    """分组子页面路由写入模型，只允许绑定具体页面。"""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(
        max_length=128,
        description="子页面路由片段，只允许单段相对路径，例如 home、chapter-1；不允许 /、/home、home/ 或 a/b。",
    )
    order: int = Field(description="同级排序值。")
    icon: str | None = Field(default=None, min_length=1, max_length=128, description="可选图标名称，通常传 null 或省略；填写时必须是当前工作空间已有的 icon 资源名。")
    hidden: bool = Field(default=False, description="是否在导航中隐藏。")
    page_id: int = Field(ge=1, description="绑定页面 ID，必须来自当前项目页面列表。")


class ProjectRouteItemWrite(BaseModel):
    """项目顶层路由写入模型，支持独立页面或页面分组。"""

    model_config = ConfigDict(extra="forbid")

    route_type: Literal["group", "page"] = Field(description="节点类型：group 表示分组，page 表示独立页面。")
    route: str = Field(
        max_length=128,
        description="顶层路由片段，只允许单段相对路径，例如 home、chapter-1；不允许 /、/home、home/ 或 a/b。",
    )
    order: int = Field(description="同级排序值。")
    icon: str | None = Field(default=None, min_length=1, max_length=128, description="可选图标名称，通常传 null 或省略；填写时必须是当前工作空间已有的 icon 资源名。")
    hidden: bool = Field(default=False, description="是否在导航中隐藏。")
    group_title: str | None = Field(default=None, min_length=1, max_length=128, description="分组标题，仅 group 节点允许。")
    page_id: int | None = Field(default=None, ge=1, description="绑定页面 ID，仅 page 节点允许，必须来自当前项目页面列表。")
    children: list[ProjectRouteChildWrite] = Field(default_factory=list, description="分组下的子页面节点，仅 group 节点允许。")

    @model_validator(mode="after")
    def validate_route_shape(self) -> "ProjectRouteItemWrite":
        """约束顶层节点只能是独立页面或分组。"""

        if self.route_type == "group":
            if self.page_id is not None:
                raise ValueError("分组节点不允许绑定页面。")
            if not str(self.group_title or "").strip():
                raise ValueError("分组节点必须提供 group_title。")
            if not self.children:
                raise ValueError("分组节点至少需要一个子页面。")
            return self

        if self.page_id is None:
            raise ValueError("页面节点必须提供 page_id。")
        if self.group_title is not None:
            raise ValueError("页面节点不允许提供 group_title。")
        if self.children:
            raise ValueError("页面节点不允许包含 children。")
        return self


class ProjectRouteTreeWriteRequest(BaseModel):
    """项目路由整树覆盖写入请求。"""

    model_config = ConfigDict(extra="forbid")

    routes: list[ProjectRouteItemWrite] = Field(default_factory=list)


class ProjectRouteChildItem(SchemaBase):
    """项目路由子页面响应模型。"""

    id: int
    route_type: Literal["page"] = "page"
    route: str
    order: int
    icon: str | None = None
    hidden: bool = False
    page_id: int
    page_code: str
    page_title: str
    display_title: str


class ProjectRouteTreeItem(SchemaBase):
    """项目顶层路由响应模型。"""

    id: int
    route_type: Literal["group", "page"]
    route: str
    order: int
    icon: str | None = None
    hidden: bool = False
    group_title: str | None = None
    page_id: int | None = None
    page_code: str | None = None
    page_title: str | None = None
    display_title: str
    children: list[ProjectRouteChildItem] = Field(default_factory=list)


class ProjectRouteTreeResponse(SchemaBase):
    """项目路由树查询响应。"""

    routes: list[ProjectRouteTreeItem] = Field(default_factory=list)
