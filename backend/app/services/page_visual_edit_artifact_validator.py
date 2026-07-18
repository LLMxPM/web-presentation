"""文件功能：严格校验页面可视化编辑 Redis artifact 的签发类型、租户、作用域和源码基线。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from app.core.exceptions import AppException
from app.schemas.page_visual_edit import (
    PageVisualEditArtifactBinding,
    PageVisualEditOperation,
    PageVisualEditSetTailwindTokensOperation,
)


@dataclass(slots=True, frozen=True)
class PageVisualEditArtifactExpectation:
    """描述当前保存请求允许使用的唯一 artifact 归属与源码基线。"""

    artifact_id: str
    user_id: int
    page_id: int
    page_version_id: int
    base_version_no: int
    source_hash: str
    module_path: str
    project_id: int
    workspace_id: int
    protocol_version: int


class PageVisualEditArtifactValidator:
    """对 Redis artifact manifest 执行 fail-closed 校验。"""

    @classmethod
    def validate(
        cls,
        manifest: dict[str, object] | None,
        expectation: PageVisualEditArtifactExpectation,
    ) -> PageVisualEditArtifactBinding:
        """校验 artifact 存在、结构可信且完整绑定当前页面版本。"""

        if manifest is None:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_EXPIRED",
                detail="可视化编辑预览已过期，请刷新预览后重试。",
            )
        cls._validate_artifact_identity(manifest, expectation)
        cls._validate_owner_scope(manifest, expectation)
        cls._validate_entry_descriptor(manifest, expectation)
        binding = cls._parse_binding(manifest)
        cls._validate_binding(binding, expectation)
        return binding

    @staticmethod
    def validate_tailwind_operations(
        binding: PageVisualEditArtifactBinding,
        operations: list[PageVisualEditOperation],
    ) -> None:
        """依据 artifact 内版本化 Catalog 预校验 Tailwind group/class，移除操作除外。"""

        allowed_classes = {
            group.key: {option.class_name for option in group.options}
            for group in binding.manifest.tailwind_catalog.groups
        }
        for operation in operations:
            if not isinstance(operation, PageVisualEditSetTailwindTokensOperation):
                continue
            for change in operation.changes:
                if change.group not in allowed_classes:
                    raise AppException(
                        status_code=422,
                        code="PAGE_VISUAL_EDIT_TAILWIND_TOKEN_UNSUPPORTED",
                        detail=f"Tailwind 可视化样式组不受支持：{change.group}。",
                    )
                if (
                    change.class_name is not None
                    and change.class_name not in allowed_classes[change.group]
                ):
                    raise AppException(
                        status_code=422,
                        code="PAGE_VISUAL_EDIT_TAILWIND_TOKEN_UNSUPPORTED",
                        detail=f"Tailwind class 不在可视化编辑白名单中：{change.class_name}。",
                    )

    @staticmethod
    def _validate_artifact_identity(
        manifest: dict[str, object],
        expectation: PageVisualEditArtifactExpectation,
    ) -> None:
        """校验 artifact 标识、类型和租户，再进入作用域与内容校验。"""

        if (
            manifest.get("artifact_id") != expectation.artifact_id
            or manifest.get("artifact_kind") != "page_visual_edit_preview"
            or manifest.get("preview_kind") != "page"
        ):
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_INVALID",
                detail="目标 artifact 不是有效的页面可视化编辑预览。",
            )
        if manifest.get("tenant_id") != f"tenant_{expectation.user_id}":
            raise AppException(
                status_code=403,
                code="PAGE_VISUAL_EDIT_ARTIFACT_SCOPE_DENIED",
                detail="目标 artifact 不属于当前用户。",
            )

    @staticmethod
    def _validate_entry_descriptor(
        manifest: dict[str, object],
        expectation: PageVisualEditArtifactExpectation,
    ) -> None:
        """在 owner scope 通过后校验页面模块入口，稳定区分错域与伪造 artifact。"""

        entry_descriptor = manifest.get("entry_descriptor")
        if not isinstance(entry_descriptor, dict) or (
            entry_descriptor.get("entry_type") != "module"
            or entry_descriptor.get("module_path") != expectation.module_path
        ):
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_INVALID",
                detail="目标 artifact 的页面模块入口不合法。",
            )

    @staticmethod
    def _validate_owner_scope(
        manifest: dict[str, object],
        expectation: PageVisualEditArtifactExpectation,
    ) -> None:
        """校验 artifact owner_scope 精确匹配页面项目和工作空间。"""

        owner_scope = manifest.get("owner_scope")
        if (
            not isinstance(owner_scope, dict)
            or owner_scope.get("scope_type") != "project"
        ):
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_INVALID",
                detail="目标 artifact 缺少有效的项目作用域。",
            )
        project_id = owner_scope.get("project_id")
        workspace_id = owner_scope.get("workspace_id")
        if not isinstance(project_id, str) or not isinstance(workspace_id, str):
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_INVALID",
                detail="目标 artifact 的项目作用域格式不合法。",
            )
        if project_id != str(expectation.project_id) or workspace_id != str(
            expectation.workspace_id
        ):
            raise AppException(
                status_code=403,
                code="PAGE_VISUAL_EDIT_ARTIFACT_SCOPE_DENIED",
                detail="目标 artifact 不属于当前页面作用域。",
            )

    @staticmethod
    def _parse_binding(manifest: dict[str, object]) -> PageVisualEditArtifactBinding:
        """以严格 Pydantic 模型解析 visual_edit，拒绝缺字段或额外字段。"""

        try:
            return PageVisualEditArtifactBinding.model_validate(
                manifest.get("visual_edit")
            )
        except ValidationError as exc:
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_INVALID",
                detail="目标 artifact 的可视化编辑元数据不合法。",
            ) from exc

    @staticmethod
    def _validate_binding(
        binding: PageVisualEditArtifactBinding,
        expectation: PageVisualEditArtifactExpectation,
    ) -> None:
        """逐字段校验 artifact 编辑基线，任何漂移都拒绝保存。"""

        if (
            binding.protocol_version != expectation.protocol_version
            or binding.page_id != expectation.page_id
            or binding.page_version_id != expectation.page_version_id
            or binding.base_version_no != expectation.base_version_no
            or binding.source_hash != expectation.source_hash
            or binding.module_path != expectation.module_path
        ):
            raise AppException(
                status_code=409,
                code="PAGE_VISUAL_EDIT_ARTIFACT_MISMATCH",
                detail="目标 artifact 与当前页面版本或源码基线不匹配。",
            )
