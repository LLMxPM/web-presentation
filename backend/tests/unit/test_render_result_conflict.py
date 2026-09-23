"""文件功能：验证渲染结果并发落库冲突后的协调器处理。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rendering import coordinator as coordinator_module

pytestmark = pytest.mark.unit


async def test_result_conflict_does_not_read_expired_attempt(monkeypatch) -> None:
    """仓储回滚使 ORM 实体过期后，协调器应使用已读取的 attempt ID 记录冲突。"""

    class ExpiringAttempt:
        """模拟仓储回滚后无法同步访问属性的 ORM attempt。"""

        request_id = 11
        expired = False

        @property
        def id(self) -> int:
            """在回滚后拒绝属性读取，暴露意外的惰性数据库访问。"""

            if self.expired:
                raise RuntimeError("attempt 已过期")
            return 7

    attempt = ExpiringAttempt()
    request = SimpleNamespace(input_digest="input", render_profile_digest="profile", request_digest="request")

    async def save_result(**_kwargs) -> None:
        """模拟另一协调器已保存结果，当前事务回滚并返回冲突。"""

        attempt.expired = True
        return None

    result_repo = SimpleNamespace(
        get_attempt=AsyncMock(return_value=attempt),
        get_request=AsyncMock(return_value=request),
        save_result=AsyncMock(side_effect=save_result),
    )
    monkeypatch.setattr(coordinator_module, "RenderRepository", lambda _session: result_repo)

    outer_session = MagicMock()
    outer_session.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [(7, "worker", "epoch", "uid")]))
    outer_session.commit = AsyncMock()
    result_session = MagicMock()
    result_session.commit = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=result_session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    receipt = SimpleNamespace(status="succeeded", result_descriptor={"result": True}, error=None)
    client = SimpleNamespace(
        fetch_execution=AsyncMock(return_value=receipt),
        confirm_result_consumption=AsyncMock(),
    )
    coordinator = coordinator_module.RenderCoordinator(session_factory=lambda: session_context, client=client)
    coordinator._endpoint_for_worker = lambda _worker_id: object()
    coordinator._materialize_result = AsyncMock(
        return_value={"payload": {}, "object_refs": {}, "environment_summary": {}}
    )

    processed = await coordinator._reconcile_running(outer_session, result_repo)

    assert processed == 0
    assert attempt.expired is True
    client.confirm_result_consumption.assert_not_awaited()
