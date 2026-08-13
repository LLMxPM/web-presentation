"""文件功能：统一解析各智能体的视觉工具槽位可用性与图片生成模型能力。"""

from __future__ import annotations

from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    IMAGE_ANALYSIS_TOOL_GROUP_KEY,
    IMAGE_GENERATION_TOOL_GROUP_KEY,
)
from app.core.exceptions import AppException
from app.services.ai_llm_service import AiLlmService
from app.services.ai_image_config_service import AiImageConfigService
from app.services.image_generation.contracts import ImageModelSpec
from app.services.image_generation.registry import get_image_model_spec

_VISUAL_AGENT_IDS = frozenset({AGENT_COORDINATOR_AGENT_ID})


async def resolve_visual_tool_runtime(
    *,
    llm_service: AiLlmService,
    agent_id: str,
    retained_tool_names: frozenset[str] = frozenset(),
) -> tuple[frozenset[str], ImageModelSpec | None, int | None]:
    """按助手能力和模型槽位解析本轮视觉工具、生成 Schema 与固定配置。"""

    if agent_id not in _VISUAL_AGENT_IDS:
        return frozenset(), None, None
    slot_lookup = await llm_service.get_slot_binding_lookup()
    unavailable: set[str] = set()
    image_generation_model: ImageModelSpec | None = None
    image_generation_config_id: int | None = None
    image_analysis_binding = slot_lookup.get("image_understanding")
    image_service = AiImageConfigService(
        llm_service.session,
        user_id=llm_service.user_id,
        user_role=llm_service.user_role,
    )
    image_generation_binding = await image_service.get_binding()
    if image_analysis_binding is None or not image_analysis_binding.binding_ready:
        unavailable.add(IMAGE_ANALYSIS_TOOL_GROUP_KEY)
    if image_generation_binding is None or not image_generation_binding.binding_ready:
        unavailable.add(IMAGE_GENERATION_TOOL_GROUP_KEY)
    else:
        try:
            image_config = await image_service._model(image_generation_binding.model_config_id, selectable=True)
            image_generation_model = get_image_model_spec(
                str(image_config.provider_config.provider_key),
                str(image_config.model_id),
            )
            image_generation_config_id = image_generation_binding.model_config_id
        except AppException:
            unavailable.add(IMAGE_GENERATION_TOOL_GROUP_KEY)
    if "analyze_visuals" in retained_tool_names:
        unavailable.discard(IMAGE_ANALYSIS_TOOL_GROUP_KEY)
    if "generate_image" in retained_tool_names:
        unavailable.discard(IMAGE_GENERATION_TOOL_GROUP_KEY)
    return frozenset(unavailable), image_generation_model, image_generation_config_id
