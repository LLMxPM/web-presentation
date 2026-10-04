"""文件功能：沿用组件首次 Mutation 的隐式基线，防止同键重放依赖当前草稿状态。"""

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.api_mutation_job import ApiMutationJob
from app.schemas.external_api import (
    ExternalComponentApplyEditsMutationRequest,
    ExternalComponentMetadataMutationRequest,
)

T = TypeVar(
    "T",
    ExternalComponentApplyEditsMutationRequest,
    ExternalComponentMetadataMutationRequest,
)


async def snapshot_component_baseline(
    session: AsyncSession,
    *,
    payload: T,
    user_id: int,
    workspace_id: int,
    operation: str,
    idempotency_key: str | None,
    current_version_no: int,
    current_draft_hash: str,
    fill_version: bool = False,
) -> T:
    """仅补齐省略基线；有效同用户/空间/operation/key 的原 Job 优先，显式值绝不改写。

    保留旧路由原有指纹顺序和 operation 命名空间；不迁移或重写历史记录，其他 payload
    字段继续参与原指纹比较。过期记录不复用旧基线，首次任务仍捕获当前版本与草稿。
    """
    frozen = {}
    if idempotency_key:
        frozen = (
            await session.scalar(
                select(ApiMutationJob.payload_json)
                .join(
                    ApiIdempotencyRecord,
                    ApiMutationJob.idempotency_record_id == ApiIdempotencyRecord.id,
                )
                .where(
                    ApiIdempotencyRecord.user_id == user_id,
                    ApiIdempotencyRecord.workspace_id == workspace_id,
                    ApiIdempotencyRecord.operation == operation,
                    ApiIdempotencyRecord.idempotency_key == idempotency_key.strip(),
                    ApiIdempotencyRecord.expires_at > utc_now(),
                    ApiMutationJob.created_by == user_id,
                    ApiMutationJob.workspace_id == workspace_id,
                    ApiMutationJob.target_id == payload.component_id,
                    ApiMutationJob.job_type.in_(
                        ("component_edit", "component_metadata")
                    ),
                )
            )
            or {}
        )
    updates = {}
    if payload.base_draft_hash is None:
        updates["base_draft_hash"] = frozen.get("base_draft_hash") or current_draft_hash
    if fill_version and payload.base_version_no is None:
        captured = frozen.get("base_version_no")
        updates["base_version_no"] = (
            current_version_no if captured is None else captured
        )
    return payload.model_copy(update=updates)
