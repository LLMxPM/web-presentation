"""文件功能：在隔离迁移库中执行实际 N-1 ORM、页面入队、旧 Batch 清扫与 Run 取消代码。"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import timedelta

import app.models  # noqa: F401
from app.ai.page_mutation_enqueue import enqueue_page_mutation
from app.ai.page_mutation_queue import (
    recover_interrupted_ai_page_mutation_jobs_on_startup,
)
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.core.time_utils import utc_now
from app.db.session import get_engine, get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentSession
from app.models.ai_page_mutation import AiPageMutationBatch
from app.models.user import User
from app.models.workspace import Workspace
from sqlalchemy import select


async def main() -> None:
    """仅允许专门的 compat_e2e；不修改并行架构演练库，更不连接开发数据库。"""
    if not os.environ.get("DATABASE_URL", "").endswith("/compat_e2e"):
        raise ValueError("旧代码 fixture 只允许 compat_e2e")
    factory = get_session_factory()
    async with factory() as session:
        suffix = str(time.time_ns())
        user = User(username="compat-" + suffix, password_hash="fixture-no-login", display_name="兼容夹具", role="platform_admin", preview_size_presets=[])
        workspace = Workspace(code="compat-" + suffix, name="兼容夹具")
        session.add_all([user, workspace])
        await session.flush()
        session_id, run_id = "legacy-session-" + suffix, "legacy-run-" + suffix
        agent_session = AiAgentSession(session_id=session_id, agent_id="agent-coordinator", user_id=user.id, workspace_id=workspace.id)
        session.add(agent_session)
        await session.flush()
        run = AiAgentRun(run_id=run_id, session_id=agent_session.session_id, agent_id="agent-coordinator", user_id=user.id,
                         workspace_id=workspace.id, scope_type="workspace", source="docker-legacy-fixture", status="running")
        session.add(run)
        await session.commit()
        user_id, workspace_id = user.id, workspace.id
    first = await enqueue_page_mutation(factory, run_id=run_id, session_id=session_id, run_step=1,
                                        tool_call_id="legacy-tool", operation="create", workspace_id=workspace_id, project_id=None)
    second = await enqueue_page_mutation(factory, run_id=run_id, session_id=session_id, run_step=1,
                                         tool_call_id="legacy-tool", operation="create", workspace_id=workspace_id, project_id=None)
    assert first.job_id == second.job_id, "旧业务幂等入队未复用 Job"
    async with factory() as session:
        batch = await session.scalar(select(AiPageMutationBatch).where(AiPageMutationBatch.batch_id == first.batch_id))
        assert batch.lease_generation == 0
        batch.lease_generation = 1
        batch.status = "resuming"
        batch.worker_id = "legacy-fixture"
        batch.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()
        session.expire_all()
        batch = await session.scalar(select(AiPageMutationBatch).where(AiPageMutationBatch.batch_id == first.batch_id))
        assert batch.lease_generation == 1
    recovered = await recover_interrupted_ai_page_mutation_jobs_on_startup(factory)
    async with factory() as session:
        batch = await session.get(AiPageMutationBatch, first.batch_id)
        assert batch.status == "completed", "旧 resuming Batch 清扫失败"
        run = await session.get(AiAgentRun, run_id)
        await PlatformAgentRuntimeStore(session, user_id=user_id).mark_terminal(run, status="cancelled", content="隔离兼容取消")
        assert run.status == "cancelled"
        report = {"status": "passed", "source_ref": "4c7eee8", "dependency_environment": "当前 Lite 镜像 Python workspace，旧 app 源码只读挂载",
                  "batch_id": first.batch_id, "job_id": first.job_id, "duplicate_job_id": second.job_id,
                  "lease_generation": batch.lease_generation, "legacy_batch_status": batch.status, "run_status": run.status, "recovered_count": recovered,
                  "scope": "完整旧 ORM SELECT/INSERT/UPDATE、真实旧页面入队幂等、过期旧 Batch 清扫、Run 取消；未执行旧模型 deferred 自动续跑与完整发布回滚"}
        print(json.dumps(report, ensure_ascii=False))
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
