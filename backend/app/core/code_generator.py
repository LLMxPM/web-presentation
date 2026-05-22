"""文件功能：提供业务编码自动生成与唯一冲突重试工具。"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.core.time_utils import get_app_date_code


# 各实体类型对应的编码前缀
CODE_PREFIX_WORKSPACE = "WS"
CODE_PREFIX_PROJECT = "PRJ"
CODE_PREFIX_PAGE = "PG"
DEFAULT_CODE_RETRY_LIMIT = 5
T = TypeVar("T")


async def generate_code(session: AsyncSession, model_class: type, prefix: str) -> str:
    """根据当天已有记录生成唯一的业务编码。

    编码格式：{prefix}{YYYYMMDD}{3位序号}，例如 WS20260328001。
    日期段基于业务时区计算，通过查询当天同前缀最大编码并递增序号来确保唯一性。
    """

    today = get_app_date_code()
    like_pattern = f"{prefix}{today}%"

    # 查询当天同前缀的最大编码（包括已软删除的，避免编码重复）
    max_code = await session.scalar(
        select(func.max(model_class.code)).where(model_class.code.like(like_pattern))
    )

    if max_code is not None:
        # 从最大编码中提取序号并递增
        seq_str = max_code[len(prefix) + 8:]  # 跳过前缀和8位日期
        next_seq = int(seq_str) + 1
    else:
        next_seq = 1

    return f"{prefix}{today}{next_seq:03d}"


async def create_with_generated_code(
    session: AsyncSession,
    model_class: type,
    prefix: str,
    write_operation: Callable[[str], Awaitable[T]],
    *,
    retry_limit: int = DEFAULT_CODE_RETRY_LIMIT,
) -> T:
    """生成业务编码并执行写入，遇到 code 唯一冲突时回滚后重试。

    write_operation 每次都会收到新的 code，并应完成对象构建、flush 以及同事务内的附属写入。
    本函数负责提交事务；只重试当前模型 code 唯一约束冲突，避免掩盖其他数据一致性问题。
    """

    last_error: IntegrityError | None = None
    for _ in range(max(retry_limit, 1)):
        code = await generate_code(session, model_class, prefix)
        try:
            result = await write_operation(code)
            await session.commit()
            return result
        except IntegrityError as error:
            await session.rollback()
            if not is_code_unique_integrity_error(error, model_class):
                raise
            last_error = error

    raise AppException(
        status_code=409,
        code="CODE_GENERATION_CONFLICT",
        detail="业务编码生成遇到并发冲突，请稍后重试。",
    ) from last_error


def is_code_unique_integrity_error(error: IntegrityError, model_class: type) -> bool:
    """判断数据库完整性错误是否为目标模型 code 字段唯一冲突。"""

    table_name = str(getattr(model_class, "__tablename__", "") or "")
    if not table_name:
        return False

    constraint_names = _collect_constraint_names(error)
    expected_constraints = {
        f"{table_name}_code_key",
        f"uq_{table_name}_code",
    }
    if constraint_names & expected_constraints:
        return True

    message = str(error).lower()
    return (
        f"{table_name}.code" in message
        or f"{table_name}_code_key" in message
        or f"uq_{table_name}_code" in message
    )


def _collect_constraint_names(error: BaseException) -> set[str]:
    """递归收集数据库驱动异常里可能携带的 constraint_name。"""

    names: set[str] = set()
    pending: list[BaseException | object | None] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        constraint_name = getattr(current, "constraint_name", None)
        if constraint_name:
            names.add(str(constraint_name))
        pending.extend(
            [
                getattr(current, "orig", None),
                getattr(current, "__cause__", None),
                getattr(current, "__context__", None),
            ]
        )
    return names
