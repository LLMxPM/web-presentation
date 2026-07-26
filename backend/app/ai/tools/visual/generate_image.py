"""文件功能：定义内容助手和资源助手使用的持久化图片生成与编辑工具入口。"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field
from pydantic_ai import CallDeferred
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.image_generation_enqueue import enqueue_image_generation
from app.ai.platform_tools import AgentToolContext, agent_tool
from app.core.exceptions import AppException


def _parse_json_array_string(value: Any) -> Any:
    """把模型偶发输出的 JSON 数组字符串还原为列表，其它值交给 Pydantic 正常校验。"""

    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return value
    return parsed if isinstance(parsed, list) else value


def build_generate_image_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建只接受附件 ID、通过 durable job 执行的图片生成工具。"""

    @agent_tool(show_result=True, sequential=True)
    async def generate_image(
        run_context: AgentToolContext,
        operation: Literal["generate", "edit"],
        prompt: Annotated[str, Field(min_length=1, max_length=8000)],
        reference_attachment_ids: Annotated[list[int], Field(max_length=4)] | None = None,
        mask_attachment_id: int | None = None,
        aspect_ratio: Literal["auto", "1:1", "3:2", "2:3"] = "auto",
        resolution_tier: Literal["auto", "standard", "high", "ultra"] = "auto",
        quality: Literal["auto", "low", "medium", "high"] = "auto",
        count: Annotated[int, Field(ge=1, le=4)] = 1,
        asset_name_prefix: Annotated[str, Field(min_length=1, max_length=120)] = "generated-image",
        description: Annotated[str | None, Field(max_length=1024)] = None,
        tags: Annotated[list[str], BeforeValidator(_parse_json_array_string), Field(max_length=20)] | None = None,
    ) -> dict[str, Any]:
        """创建图片生成或编辑任务；完成后自动保存资源并恢复父 run。"""

        references = list(dict.fromkeys(reference_attachment_ids or []))
        normalized_prompt = prompt.strip()
        normalized_prefix = asset_name_prefix.strip()
        if not normalized_prompt:
            raise AppException(status_code=422, code="AI_IMAGE_GENERATION_PROMPT_REQUIRED", detail="图片生成或编辑提示词不能为空。")
        if not normalized_prefix:
            raise AppException(status_code=422, code="AI_IMAGE_ASSET_NAME_REQUIRED", detail="图片资源名称前缀不能为空。")
        if operation == "edit" and not references:
            raise AppException(status_code=422, code="AI_IMAGE_EDIT_SOURCE_REQUIRED", detail="编辑图片至少需要一张参考或源图片附件。")
        if operation == "generate" and mask_attachment_id is not None:
            raise AppException(status_code=422, code="AI_IMAGE_MASK_OPERATION_INVALID", detail="蒙版只能用于图片编辑。")
        dependencies = run_context.dependencies
        deferred_tool_call_id = str(dependencies.get("current_tool_call_id") or "").strip()
        if not deferred_tool_call_id:
            raise AppException(status_code=409, code="AI_IMAGE_GENERATION_CONTEXT_REQUIRED", detail="图片生成必须在持久化工具调用上下文中执行。")
        member_run_id = str(dependencies.get("member_run_id") or "").strip() or None
        tool_call_id = (
            f"{member_run_id}:{deferred_tool_call_id}"
            if member_run_id
            else deferred_tool_call_id
        )
        enqueued = await enqueue_image_generation(
            session_factory,
            run_id=run_context.run_id,
            session_id=run_context.session_id,
            tool_call_id=tool_call_id,
            deferred_tool_call_id=deferred_tool_call_id,
            member_run_id=member_run_id,
            user_id=int(dependencies.get("user_id") or 0),
            workspace_id=int(dependencies.get("workspace_id") or 0),
            project_id=int(dependencies["project_id"]) if dependencies.get("project_id") is not None else None,
            model_config_id=(
                int(dependencies["image_generation_config_id"])
                if dependencies.get("image_generation_config_id") is not None
                else None
            ),
            request_payload={
                "operation": operation,
                "prompt": normalized_prompt,
                "reference_attachment_ids": references,
                "mask_attachment_id": mask_attachment_id,
                "aspect_ratio": aspect_ratio,
                "resolution_tier": resolution_tier,
                "quality": quality,
                "count": count,
                "asset_name_prefix": normalized_prefix,
                "description": description,
                "tags": [str(tag).strip() for tag in tags or [] if str(tag).strip()],
            },
        )
        raise CallDeferred(metadata=enqueued.as_metadata())

    return generate_image
