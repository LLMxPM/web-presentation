"""文件功能：提供 E2E 测试就绪指纹端点，供 ensure-services 校验环境；非 mock 模式返回 404。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.testing_environment import database_profile, redis_profile
from app.db.session import get_db_session
from app.models.ai_llm import AiLlmConfig, AiLlmProviderConfig, AiLlmSlotBinding
from app.models.enums import AiLlmSlot, RecordStatus
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter()

_READINESS_SLOTS = (
    AiLlmSlot.AGENT_COORDINATOR.value,
    AiLlmSlot.IMAGE_UNDERSTANDING.value,
    AiLlmSlot.IMAGE_GENERATION.value,
)
_EXPECTED_SLOT_MODEL_PREFIXES = {
    AiLlmSlot.AGENT_COORDINATOR.value: "e2e-mock-agent-",
    AiLlmSlot.IMAGE_UNDERSTANDING.value: "e2e-mock-vision-",
    AiLlmSlot.IMAGE_GENERATION.value: "e2e-mock-image-",
}


@router.get("/e2e-readiness")
async def get_e2e_readiness(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """返回不含连接串和密钥的测试就绪信息；非 mock 模式该入口不可达。"""

    settings = get_settings()
    if settings.ai_test_mode != "mock":
        raise AppException(
            status_code=404,
            code="TESTING_READINESS_UNAVAILABLE",
            detail="测试就绪端点仅在 AI_TEST_MODE=mock 下可用。",
        )

    from app.ai.testing.scenarios import SCENARIO_VERSION
    from app.scripts.test_data import SEED_VERSION, SMOKE_DATA

    return {
        "test_mode": "mock",
        "database_profile": database_profile(settings),
        "redis_profile": redis_profile(settings),
        "seed_version": SEED_VERSION,
        "scenario_version": SCENARIO_VERSION,
        "smoke_data_ready": await _smoke_data_ready(
            session,
            workspace_name=SMOKE_DATA.workspace_name,
            admin_username=settings.default_admin_username,
        ),
    }


async def _smoke_data_ready(session: AsyncSession, *, workspace_name: str, admin_username: str) -> bool:
    """判断 smoke 工作空间存在，且管理员三个槽位绑定到启用中的正确 mock 模型。"""

    workspace_id = await session.scalar(select(Workspace.id).where(Workspace.name == workspace_name))
    if workspace_id is None:
        return False
    admin_id = await session.scalar(select(User.id).where(User.username == admin_username))
    if admin_id is None:
        return False
    bindings = (
        await session.execute(
            select(AiLlmSlotBinding.slot, AiLlmConfig.model_id)
            .join(AiLlmConfig, AiLlmConfig.id == AiLlmSlotBinding.llm_config_id)
            .join(AiLlmProviderConfig, AiLlmProviderConfig.id == AiLlmConfig.provider_config_id)
            .where(
                AiLlmSlotBinding.user_id == admin_id,
                AiLlmSlotBinding.slot.in_(_READINESS_SLOTS),
                AiLlmSlotBinding.llm_config_id.is_not(None),
                AiLlmConfig.status == RecordStatus.ACTIVE.value,
                AiLlmProviderConfig.status == RecordStatus.ACTIVE.value,
            )
        )
    ).all()
    bound_models = {slot: model_id for slot, model_id in bindings}
    return all(
        str(bound_models.get(slot) or "").startswith(prefix)
        for slot, prefix in _EXPECTED_SLOT_MODEL_PREFIXES.items()
    )
