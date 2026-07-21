"""文件功能：按智能体授权边界统一分析会话附件、资源图片和页面截图。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PAGE_TOOL_VISUAL_SCOPES, RESOURCE_TOOL_READ_SCOPES, extract_user_id
from app.ai.image_refs import build_agent_image_ref
from app.ai.platform_tools import AgentToolContext, agent_tool
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.models.enums import AssetType, RecordStatus
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.asset_service import AssetService
from app.services.image_understanding_service import ImageUnderstandingInput, ImageUnderstandingService
from app.services.page_screenshot_job_service import PageScreenshotJobService


class AttachmentVisualInput(BaseModel):
    """引用当前会话中的真实图片附件。"""

    model_config = ConfigDict(extra="forbid")
    source_type: Literal["attachment"]
    attachment_id: int = Field(gt=0)


class PageScreenshotVisualInput(BaseModel):
    """引用当前业务范围内页面的最新截图。"""

    model_config = ConfigDict(extra="forbid")
    source_type: Literal["page_screenshot"]
    page_id: int = Field(gt=0)


class AssetVisualInput(BaseModel):
    """引用当前工作空间资源库中的可分析图片。"""

    model_config = ConfigDict(extra="forbid")
    source_type: Literal["asset"]
    asset_id: int = Field(gt=0)


VisualInput = Annotated[
    AttachmentVisualInput | PageScreenshotVisualInput | AssetVisualInput,
    Field(discriminator="source_type"),
]
_VISUAL_INPUTS_ADAPTER = TypeAdapter(list[VisualInput])
_SUPPORTED_ASSET_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_ASSET_IMAGE_SUFFIX_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def build_analyze_visuals_tool(session_factory: async_sessionmaker[AsyncSession]):
    """构建统一视觉分析工具；图片只发送给独立图片理解模型。"""

    @agent_tool(show_result=True, sequential=True)
    async def analyze_visuals(
        run_context: AgentToolContext,
        inputs: Annotated[list[VisualInput], Field(min_length=1, max_length=4)],
        instruction: Annotated[str, Field(min_length=1, max_length=4000)],
        analysis_type: Literal["general", "ocr", "layout", "comparison", "presentation_fit"] = "general",
        detail: Literal["low", "auto", "high"] = "auto",
    ) -> dict[str, Any]:
        """按统一输入约定分析附件或页面截图，并返回同一种结构化结果。"""

        normalized_inputs = _VISUAL_INPUTS_ADAPTER.validate_python(inputs)
        _validate_unique_inputs(normalized_inputs)
        _validate_allowed_input_types(run_context, normalized_inputs)
        normalized_instruction = instruction.strip()
        if not normalized_instruction:
            raise AppException(status_code=422, code="AI_IMAGE_ANALYSIS_INSTRUCTION_REQUIRED", detail="图片理解指令不能为空。")

        dependencies, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=_required_scopes(normalized_inputs),
            required_dependency_fields=("workspace_id",),
        )
        user_id = extract_user_id(claims.get("sub"))
        workspace_id = int(dependencies["workspace_id"])
        project_id = _coerce_optional_int(dependencies.get("project_id"))
        run_id = str(run_context.run_id or dependencies.get("run_id") or "")
        session_id = str(run_context.session_id or dependencies.get("session_id") or "")

        async with session_factory() as session:
            image_service = AgentImageAttachmentService(session, user_id=user_id)
            attachment_ids = [item.attachment_id for item in normalized_inputs if isinstance(item, AttachmentVisualInput)]
            attachments = await image_service.validate_attachments_for_run(
                workspace_id=workspace_id,
                session_id=session_id,
                attachment_ids=attachment_ids,
            )
            attachment_by_id = {item.id: item for item in attachments}
            asset_service = AssetService(session)
            analysis_inputs: list[ImageUnderstandingInput] = []
            for item in normalized_inputs:
                if isinstance(item, AttachmentVisualInput):
                    attachment = attachment_by_id[item.attachment_id]
                    content = await image_service.object_storage_service.read_object(attachment.storage_key)
                    analysis_inputs.append(_attachment_analysis_input(attachment, content))
                    continue
                if isinstance(item, AssetVisualInput):
                    analysis_inputs.append(
                        await _resolve_asset_input(
                            asset_service=asset_service,
                            image_service=image_service,
                            item=item,
                            user_id=user_id,
                            workspace_id=workspace_id,
                            session_id=session_id,
                            run_id=run_id,
                            tool_name=str(dependencies.get("current_tool_name") or "analyze_visuals"),
                            tool_call_id=str(dependencies.get("current_tool_call_id") or ""),
                        )
                    )
                    continue
                analysis_inputs.append(
                    await _resolve_page_screenshot_input(
                        session=session,
                        image_service=image_service,
                        item=item,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        project_id=project_id,
                        session_id=session_id,
                        run_id=run_id,
                        tool_name=str(dependencies.get("current_tool_name") or "analyze_visuals"),
                        tool_call_id=str(dependencies.get("current_tool_call_id") or ""),
                    )
                )
            return await ImageUnderstandingService(session, user_id=user_id).analyze(
                inputs=analysis_inputs,
                instruction=normalized_instruction,
                analysis_type=analysis_type,
                detail=detail,
            )

    return analyze_visuals


async def _resolve_asset_input(
    *,
    asset_service: AssetService,
    image_service: AgentImageAttachmentService,
    item: AssetVisualInput,
    user_id: int,
    workspace_id: int,
    session_id: str,
    run_id: str,
    tool_name: str,
    tool_call_id: str,
) -> ImageUnderstandingInput:
    """校验并读取工作空间图片资源，登记会话预览附件后生成视觉输入。"""

    asset = await asset_service._get_asset_or_raise(workspace_id, item.asset_id)
    if (
        asset.status != RecordStatus.ACTIVE.value
        or asset.source_asset_id is not None
        or asset.history_kind is not None
    ):
        raise AppException(status_code=409, code="AI_VISUAL_ASSET_INACTIVE", detail="视觉分析只支持资源库中启用的普通资源。")
    if asset.asset_type not in {AssetType.IMAGE.value, AssetType.ICON.value}:
        raise AppException(status_code=422, code="AI_VISUAL_ASSET_TYPE_UNSUPPORTED", detail="视觉分析只支持图片或图标资源。")
    content_type = _resolve_asset_image_content_type(asset.original_name, asset.content_type)
    max_bytes = int(image_service.settings.ai_image_attachment_max_bytes)
    if int(asset.file_size or 0) > max_bytes:
        raise AppException(status_code=413, code="AI_VISUAL_ASSET_TOO_LARGE", detail="资源图片超过视觉分析单图大小上限。")
    content = await asset_service.driver.read_content(workspace_id, asset.file_name)
    if len(content) > max_bytes:
        raise AppException(status_code=413, code="AI_VISUAL_ASSET_TOO_LARGE", detail="资源图片超过视觉分析单图大小上限。")
    attachment = await image_service.register_tool_image(
        workspace_id=workspace_id,
        session_id=session_id,
        run_id=run_id,
        content=content,
        original_name=asset.original_name,
        content_type=content_type,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        source_payload={"asset_id": asset.id, "asset_name": asset.name, "asset_type": asset.asset_type},
        operator_id=user_id,
    )
    return ImageUnderstandingInput(
        source={
            "source_type": "asset",
            "asset_id": asset.id,
            "asset_name": asset.name,
            "asset_type": asset.asset_type,
            "original_name": asset.original_name,
            "attachment_id": attachment.id,
            "preview_ref": build_agent_image_ref(attachment),
        },
        content=content,
        content_type=content_type,
        width=attachment.width,
        height=attachment.height,
    )


async def _resolve_page_screenshot_input(
    *,
    session: AsyncSession,
    image_service: AgentImageAttachmentService,
    item: PageScreenshotVisualInput,
    user_id: int,
    workspace_id: int,
    project_id: int | None,
    session_id: str,
    run_id: str,
    tool_name: str,
    tool_call_id: str,
) -> ImageUnderstandingInput:
    """获取页面最新截图、登记预览附件，并生成可信视觉输入。"""

    screenshot = await PageScreenshotJobService(session).ensure_latest_page_screenshot_via_queue(
        page_id=item.page_id,
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    attachment = await image_service.register_tool_image(
        workspace_id=workspace_id,
        session_id=session_id,
        run_id=run_id,
        content=screenshot.content,
        original_name=f"{screenshot.page.code}.png",
        content_type="image/png",
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        source_payload={
            "page_id": screenshot.page.id,
            "page_code": screenshot.page.code,
            "page_version_no": screenshot.page.screenshot_version_no,
            "screenshot_refreshed": screenshot.refreshed,
        },
        operator_id=user_id,
    )
    source = {
        "source_type": "page_screenshot",
        "page_id": screenshot.page.id,
        "page_code": screenshot.page.code,
        "page_title": screenshot.page.title,
        "attachment_id": attachment.id,
        "page_version_no": screenshot.page.screenshot_version_no,
        "screenshot_refreshed": screenshot.refreshed,
        "preview_ref": build_agent_image_ref(attachment),
    }
    return ImageUnderstandingInput(
        source=source,
        content=screenshot.content,
        content_type=attachment.content_type,
        width=attachment.width,
        height=attachment.height,
    )


def _attachment_analysis_input(attachment: Any, content: bytes) -> ImageUnderstandingInput:
    """把已完成会话权限校验的附件转换为统一视觉输入。"""

    return ImageUnderstandingInput(
        source={
            "source_type": "attachment",
            "attachment_id": attachment.id,
            "original_name": attachment.original_name,
            "preview_ref": build_agent_image_ref(attachment),
        },
        content=content,
        content_type=attachment.content_type,
        width=attachment.width,
        height=attachment.height,
    )


def _validate_unique_inputs(inputs: list[VisualInput]) -> None:
    """拒绝同一次调用中的重复来源，避免浪费视觉模型配额。"""

    keys = []
    for item in inputs:
        if isinstance(item, AttachmentVisualInput):
            source_id = item.attachment_id
        elif isinstance(item, PageScreenshotVisualInput):
            source_id = item.page_id
        else:
            source_id = item.asset_id
        keys.append((item.source_type, source_id))
    if len(set(keys)) != len(keys):
        raise AppException(status_code=422, code="AI_VISUAL_INPUT_DUPLICATED", detail="视觉分析输入不能重复。")


def _validate_allowed_input_types(run_context: AgentToolContext, inputs: list[VisualInput]) -> None:
    """拒绝智能体边界之外的视觉输入，即使调用绕过模型 Schema。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    allowed = {str(item) for item in dependencies.get("allowed_visual_input_types") or [] if str(item)}
    requested = {item.source_type for item in inputs}
    if not requested.issubset(allowed):
        raise AppException(
            status_code=403,
            code="AI_VISUAL_INPUT_SOURCE_DENIED",
            detail="当前助手不能访问所请求的视觉输入类型。",
        )


def _required_scopes(inputs: list[VisualInput]) -> tuple[str, ...]:
    """按本次实际输入汇总最小工具权限。"""

    scopes: list[str] = []
    if any(isinstance(item, AssetVisualInput) for item in inputs):
        scopes.extend(RESOURCE_TOOL_READ_SCOPES)
    if any(isinstance(item, PageScreenshotVisualInput) for item in inputs):
        scopes.extend(PAGE_TOOL_VISUAL_SCOPES)
    return tuple(dict.fromkeys(scopes))


def _resolve_asset_image_content_type(original_name: str, raw_content_type: str | None) -> str:
    """把资源 MIME 规整为图片理解与会话附件共同支持的位图类型。"""

    normalized_type = str(raw_content_type or "").split(";", 1)[0].strip().lower()
    suffix_type = _ASSET_IMAGE_SUFFIX_TYPES.get(Path(original_name).suffix.lower())
    content_type = normalized_type if normalized_type in _SUPPORTED_ASSET_IMAGE_TYPES else suffix_type
    if content_type is None:
        raise AppException(
            status_code=422,
            code="AI_VISUAL_ASSET_FORMAT_UNSUPPORTED",
            detail="资源图片分析仅支持 png、jpg、jpeg、webp；SVG、GIF 等格式暂不支持。",
        )
    return content_type


def _coerce_optional_int(value: Any) -> int | None:
    """把可选上下文字段转为整数。"""

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
