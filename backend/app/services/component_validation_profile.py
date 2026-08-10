"""文件功能：定义组件 check 的版本化执行期预览环境，避免隐式继承当前焦点项目页面配置。"""

from __future__ import annotations

from app.models.enums import WorkspaceComponentType
from app.schemas.component_preview_options import (
    ComponentPreviewOptions,
    ComponentPreviewPageOptions,
    ComponentPreviewPlacementOptions,
)

COMPONENT_VALIDATION_PROFILE_VERSION = "component-profiles.v1"


def build_component_validation_profile(
    component_type: WorkspaceComponentType,
) -> tuple[str, ComponentPreviewOptions]:
    """按组件类型构造稳定的临时校验 profile；其中页面参数不是组件持久属性。"""

    page = ComponentPreviewPageOptions()
    if component_type == WorkspaceComponentType.PAGE_COMPONENT:
        return (
            "component-page-landscape.v1",
            ComponentPreviewOptions(
                page=page,
                placement=ComponentPreviewPlacementOptions(
                    width_mode="percent",
                    width_value=100,
                    height_mode="percent",
                    height_value=100,
                    padding=0,
                ),
            ),
        )
    if component_type == WorkspaceComponentType.ATOMIC_COMPONENT:
        return (
            "component-atomic-default.v1",
            ComponentPreviewOptions(
                page=page,
                placement=ComponentPreviewPlacementOptions(
                    width_mode="fixed",
                    width_value=640,
                    height_mode="fixed",
                    height_value=360,
                    padding=48,
                ),
            ),
        )
    return (
        "component-content-default.v1",
        ComponentPreviewOptions(
            page=page,
            placement=ComponentPreviewPlacementOptions(
                width_mode="fixed",
                width_value=960,
                height_mode="fixed",
                height_value=540,
                padding=48,
            ),
        ),
    )
