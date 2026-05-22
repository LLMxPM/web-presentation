"""文件功能：验证业务编码生成 helper 的唯一冲突识别与重试行为。"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.code_generator import create_with_generated_code
from app.core.time_utils import get_app_date_code
from app.models.page import Page


class ConstraintError(Exception):
    """测试用数据库约束异常，模拟驱动层 constraint_name。"""

    def __init__(self, constraint_name: str) -> None:
        super().__init__(constraint_name)
        self.constraint_name = constraint_name


class FakeSession:
    """测试用最小异步 Session，只实现编码 helper 需要的方法。"""

    def __init__(self) -> None:
        self.scalar_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def scalar(self, _) -> str | None:
        """第一次表示当天无记录，后续返回已存在最大编码。"""

        self.scalar_count += 1
        if self.scalar_count == 1:
            return None
        return f"PG{get_app_date_code()}001"

    async def commit(self) -> None:
        """记录提交次数。"""

        self.commit_count += 1

    async def rollback(self) -> None:
        """记录回滚次数。"""

        self.rollback_count += 1


def _integrity_error(constraint_name: str) -> IntegrityError:
    """构造带约束名的 SQLAlchemy 完整性错误。"""

    return IntegrityError("insert", {}, ConstraintError(constraint_name))


async def test_create_with_generated_code_should_retry_code_unique_conflict() -> None:
    """目标表 code 唯一冲突时应回滚并重新生成业务编码。"""

    session = FakeSession()
    seen_codes: list[str] = []

    async def write_operation(code: str) -> str:
        """首次写入模拟 pages.code 冲突，第二次成功返回 code。"""

        seen_codes.append(code)
        if len(seen_codes) == 1:
            raise _integrity_error("pages_code_key")
        return code

    created_code = await create_with_generated_code(session, Page, "PG", write_operation)

    assert created_code == f"PG{get_app_date_code()}002"
    assert seen_codes == [f"PG{get_app_date_code()}001", f"PG{get_app_date_code()}002"]
    assert session.rollback_count == 1
    assert session.commit_count == 1


async def test_create_with_generated_code_should_not_retry_other_integrity_error() -> None:
    """非目标 code 约束冲突应原样抛出，避免掩盖真实数据问题。"""

    session = FakeSession()
    seen_codes: list[str] = []

    async def write_operation(code: str) -> str:
        """模拟页面版本号唯一约束冲突。"""

        seen_codes.append(code)
        raise _integrity_error("uq_page_versions_page_id_version_no")

    with pytest.raises(IntegrityError):
        await create_with_generated_code(session, Page, "PG", write_operation)

    assert seen_codes == [f"PG{get_app_date_code()}001"]
    assert session.rollback_count == 1
    assert session.commit_count == 0
