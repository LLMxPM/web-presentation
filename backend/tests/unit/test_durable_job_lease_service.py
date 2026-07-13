"""文件功能：验证持久化任务租约服务在空闲恢复时不放大 SQLite 写操作。"""

from __future__ import annotations

import pytest

from app.models.ai_page_mutation import AiPageMutationJob
from app.services.durable_job_lease_service import recover_expired_running_jobs


class _EmptyRecoveryResult:
    """模拟未找到过期任务的只读查询结果。"""

    def all(self) -> list[object]:
        """返回空候选列表。"""

        return []


class _RecordingRecoverySession:
    """记录恢复流程执行的语句数量，避免测试依赖真实数据库。"""

    def __init__(self) -> None:
        """初始化语句与提交计数。"""

        self.statements: list[object] = []
        self.commit_count = 0

    async def execute(self, statement: object) -> _EmptyRecoveryResult:
        """记录只读查询；空队列时任何后续 DML 都会增加调用次数。"""

        self.statements.append(statement)
        return _EmptyRecoveryResult()

    async def commit(self) -> None:
        """结束只读事务。"""

        self.commit_count += 1


@pytest.mark.asyncio
async def test_recover_expired_jobs_should_not_issue_dml_when_queue_is_empty() -> None:
    """空闲恢复只能执行候选 SELECT，不能额外发送无命中 UPDATE。"""

    session = _RecordingRecoverySession()

    summary = await recover_expired_running_jobs(
        session,  # type: ignore[arg-type]
        AiPageMutationJob,
        max_attempts=3,
        interrupted_error_code="TEST_INTERRUPTED",
        interrupted_error_message="测试中断。",
    )

    assert summary.total_count == 0
    assert len(session.statements) == 1
    assert session.commit_count == 1
