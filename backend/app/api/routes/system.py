"""文件功能：提供平台级系统默认值，供前端初始化表单时读取。"""

from fastapi import APIRouter

from app.schemas.project_app_config import DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN

router = APIRouter()


@router.get("/system/default-style-spec")
async def get_default_style_spec() -> dict[str, str]:
    """返回平台级默认 Markdown 样式规范，作为前端表单初始值的统一来源。"""

    return {"style_spec_markdown": DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN}
