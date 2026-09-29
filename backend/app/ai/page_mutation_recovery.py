"""文件功能：在同一事务恢复过期页面任务并写穿统一 ExternalTask，供启动与循环恢复共用。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.external_task_control import sync_external_task_from_domain_job
from app.ai.job_invariants import finalize_external_backed_job
from app.ai.task_states import EXTERNAL_TASK_TERMINAL_STATUSES
from app.models.ai_page_mutation import AiPageMutationJob
from app.services.durable_job_lease_service import (
    DurableJobRecoverySummary,
    recover_expired_running_jobs,
)


async def recover_page_mutation_jobs(session: AsyncSession, *, max_attempts: int) -> DurableJobRecoverySummary:
    """恢复成功的行在提交前同步 Task；投影失败时由共享恢复器回滚整批更新。"""

    async def _sync_recovered_job(job_id: int) -> None:
        """重读 CAS 更新后的实际状态，避免 ORM 缓存把旧状态投影回 Task。"""

        job = await session.get(AiPageMutationJob, job_id, populate_existing=True)
        if job is None:
            raise RuntimeError(f"恢复中的页面任务不存在：{job_id}")
        if job.status in EXTERNAL_TASK_TERMINAL_STATUSES:
            await finalize_external_backed_job(session, job=job, status=job.status)
        else:
            await sync_external_task_from_domain_job(session, job=job)

    return await recover_expired_running_jobs(
        session,
        AiPageMutationJob,
        max_attempts=max_attempts,
        interrupted_error_code="AI_PAGE_MUTATION_INTERRUPTED",
        interrupted_error_message="页面变更任务执行中断且已达到最大重试次数。",
        on_recovered=_sync_recovered_job,
    )
