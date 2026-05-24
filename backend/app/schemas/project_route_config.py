"""文件功能：定义项目级路由 YAML 的结构模型，约束叶子路由使用 page_code 绑定页面资源。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectRouteMeta(BaseModel):
    """路由元信息，描述标题、排序和展示控制字段。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=128)
    order: int
    hidden: bool | None = None


class ProjectRoutePageRefMixin(BaseModel):
    """叶子路由页面引用混入，只允许按业务编码定位页面。"""

    page_code: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_page_ref(self):
        """要求叶子路由必须提供 page_code，且不允许继续使用 page_id。"""

        has_page_code = bool(self.page_code)
        extra_fields = getattr(self, "__pydantic_extra__", None) or {}
        if "page_id" in extra_fields:
            raise ValueError("叶子路由不再支持 page_id，请改用 page_code。")
        if not has_page_code:
            raise ValueError("叶子路由必须配置 page_code。")
        return self


class ProjectRouteChildConfig(ProjectRoutePageRefMixin):
    """子页面路由配置，必须通过页面标识绑定一个页面。"""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(min_length=1, max_length=128)
    meta: ProjectRouteMeta


class ProjectRouteItemConfig(ProjectRoutePageRefMixin):
    """顶层路由配置，支持分组路由或独立页面两种形态。"""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(min_length=1, max_length=128)
    meta: ProjectRouteMeta
    children: list[ProjectRouteChildConfig] | None = None

    @model_validator(mode="after")
    def validate_route_shape(self) -> "ProjectRouteItemConfig":
        """约束顶层路由只能是“分组”或“页面”二选一。"""

        has_children = bool(self.children)
        has_page_ref = bool(self.page_code)
        if has_children and has_page_ref:
            raise ValueError("带 children 的分组路由不允许配置 page_code。")
        if not has_children and not has_page_ref:
            raise ValueError("独立页面必须配置 page_code。")
        return self


class ProjectRouteConfigDocument(BaseModel):
    """项目级 routes.config.yaml 根节点。"""

    model_config = ConfigDict(extra="forbid")

    routes: list[ProjectRouteItemConfig] = Field(default_factory=list)
