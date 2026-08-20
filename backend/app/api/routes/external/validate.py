"""文件功能：提供 External API v1 源码独立语法与依赖合法性校验接口。"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, get_external_auth_context
from app.core.component_preview_schema import validate_component_preview_schema_text
from app.core.exceptions import AppException
from app.core.runtime_module_policy import (
    RUNTIME_KIT_ALIAS,
    RUNTIME_REMOTE_COMPONENT_PREFIX,
    get_runtime_kit_capability_by_import_path,
)
from app.db.session import get_db_session
from app.schemas.external_api import ExternalValidateCodeRequest, ExternalValidateCodeResponse

router = APIRouter()

_IMPORT_REGEX = re.compile(
    r"""(?:import\s+(?:(?:\*\s+as\s+\w+|[\w\s{},]+)\s+from\s+)?['"](?P<module>[^'"]+)['"])|(?:import\s*\(\s*['"](?P<dyn_module>[^'"]+)['"]\s*\))"""
)


@router.post("/code", response_model=ExternalValidateCodeResponse)
async def validate_source_code(
    payload: ExternalValidateCodeRequest,
    auth: Annotated[ExternalAuthContext, Depends(get_external_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalValidateCodeResponse:
    """独立校验 Vue 页面或工作空间组件源码的合法性与 Runtime Kit 依赖契约（支持 page 或 component 权限）。"""

    # 权限校验：页面校验需要 page:read，组件校验需要 component:read
    required_scope = "page:read" if payload.entity_type == "page" else "component:read"
    if not auth.has_scope(required_scope):
        raise AppException(
            status_code=403,
            code="INSUFFICIENT_SCOPE",
            detail=f"校验 {payload.entity_type} 源码需要 {required_scope} 权限 Scope。",
            data={"required_scopes": [required_scope]},
        )

    errors: list[str] = []
    warnings: list[str] = []
    imports: list[str] = []

    # 1. 基础 SFC 结构校验
    code = payload.source_code.strip()
    if not code:
        errors.append("源码不能为空。")
        return ExternalValidateCodeResponse(valid=False, errors=errors, warnings=warnings, imports=imports)

    has_template = "<template" in code and "</template>" in code
    has_script = "<script" in code and "</script>" in code

    if not has_template and not has_script:
        errors.append("Vue 源码必须至少包含 <template> 或 <script> 代码块。")

    # 2. 导入依赖校验
    for match in _IMPORT_REGEX.finditer(code):
        mod = match.group("module") or match.group("dyn_module")
        if not mod:
            continue
        imports.append(mod)

        if mod.startswith(RUNTIME_KIT_ALIAS):
            dep = get_runtime_kit_capability_by_import_path(mod)
            if dep is None:
                errors.append(
                    f"未知的 @runtime-kit 依赖: '{mod}'。必须引用 manifest 中声明的带 .vN 版本化公开路径。"
                )
        elif mod.startswith(RUNTIME_REMOTE_COMPONENT_PREFIX):
            pass  # 工作空间组件引用
        elif mod.startswith("vue") or mod.startswith("@vue/"):
            pass  # Vue 基础运行时
        elif mod.startswith("./") or mod.startswith("../") or mod.startswith("@/"):
            warnings.append(f"相对路径或内部别名导入 '{mod}' 可能在独立 Runtime 环境中无法正常解析。")
        else:
            warnings.append(f"外部裸模块导入 '{mod}' 依赖 Runtime Kit 宿主环境提供。")

    # 3. 组件 preview_schema 校验
    if payload.entity_type == "component" and payload.preview_schema is not None:
        try:
            validate_component_preview_schema_text(payload.preview_schema)
        except Exception as schema_err:
            errors.append(f"组件 preview_schema 校验失败: {schema_err}")

    is_valid = len(errors) == 0
    return ExternalValidateCodeResponse(
        valid=is_valid,
        errors=errors,
        warnings=warnings,
        imports=list(set(imports)),
    )
