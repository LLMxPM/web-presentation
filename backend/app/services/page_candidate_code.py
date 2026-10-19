"""文件功能：为页面创建任务规划稳定编码，保存冲突时必须重新规划而不能换码发布旧图。"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_PAGE, generate_code
from app.models.ai_page_mutation import AiPageMutationJob
from app.models.api_mutation_job import ApiMutationJob
from app.models.page import Page


async def plan_candidate_code(session: AsyncSession, previous: str | None = None) -> str:
    """复用未被业务页面占用的持久编码；新编码避开当前两类任务已规划的序号。"""
    if previous and not await session.scalar(select(Page.id).where(Page.code == previous)):
        return previous
    generated = await generate_code(session, Page, CODE_PREFIX_PAGE)
    prefix = generated[:10]
    sequence = int(generated[10:])
    for model in (AiPageMutationJob, ApiMutationJob):
        maximum = await session.scalar(select(func.max(model.candidate_code)).where(model.candidate_code.like(f"{prefix}%")))
        if maximum and maximum[10:].isdigit():
            sequence = max(sequence, int(maximum[10:]) + 1)
    return f"{prefix}{sequence:03d}"
