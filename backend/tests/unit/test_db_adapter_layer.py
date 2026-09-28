"""文件功能：验证 app/db 持久化适配层的写冲突判据、打点副作用与锁探测边界。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from app.db import metrics as write_path_metrics
from app.db.errors import detect_transient_write_conflict
from app.db.locks import holds_write_lock


@pytest.fixture(autouse=True)
def _isolated_metrics():
    """打点是全局进程状态；每个用例前后清空，避免互相污染。"""

    write_path_metrics.reset()
    write_path_metrics.set_metrics_enabled(True)
    yield
    write_path_metrics.set_metrics_enabled(False)
    write_path_metrics.reset()


def test_sqlite_busy_is_retryable_and_counted() -> None:
    """SQLite database is locked 应识别为可重试写冲突，并打点一次。"""

    exc = OperationalError("UPDATE t", {}, Exception("database is locked"))
    assert detect_transient_write_conflict(exc) is True
    assert write_path_metrics.snapshot()["totals"]["write_conflicts"] == 1


def test_pg_serialization_failure_is_retryable_and_counted() -> None:
    """PostgreSQL serialization_failure(40001) 应识别为可重试，且与 SQLite 口径一致地打点。"""

    class _Orig(Exception):
        pgcode = "40001"

    exc = OperationalError("UPDATE t", {}, _Orig("could not serialize"))
    assert detect_transient_write_conflict(exc) is True
    assert write_path_metrics.snapshot()["totals"]["write_conflicts"] == 1


def test_pg_deadlock_is_retryable() -> None:
    """PostgreSQL deadlock_detected(40P01) 应识别为可重试。"""

    class _Orig(Exception):
        pgcode = "40P01"

    assert detect_transient_write_conflict(OperationalError("UPDATE t", {}, _Orig("deadlock"))) is True


def test_non_conflict_error_is_not_retryable_and_not_counted() -> None:
    """普通语法错误不得触发重试，也不得污染写冲突计数。"""

    exc = OperationalError("SELECT bad", {}, Exception("syntax error"))
    assert detect_transient_write_conflict(exc) is False
    assert write_path_metrics.snapshot()["totals"]["write_conflicts"] == 0


def test_holds_write_lock_non_sqlite_is_false() -> None:
    """非 SQLite 会话恒 False。"""

    class _Bind:
        dialect = type("D", (), {"name": "postgresql"})()

    class _Session:
        def get_bind(self):
            return _Bind()

    assert holds_write_lock(_Session()) is False


def test_driver_connection_only_in_db_locks() -> None:
    """防漂移：driver_connection 下钻只允许出现在 app/db/locks.py。"""

    offenders = [
        rel
        for rel, source in _backend_sources("app")
        if rel != "app/db/locks.py" and "driver_connection" in source
    ]
    assert offenders == []


def test_write_conflict_predicate_has_single_definition() -> None:
    """防漂移：写冲突判据只在 app/db/errors.py 定义一次，不得再出现兼容别名。"""

    names = {"detect_transient_write_conflict", "is_sqlite_lock_error", "is_transient_write_error"}
    definitions: list[str] = []
    for rel, source in _backend_sources("app"):
        tree = ast.parse(source, filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in names:
                definitions.append(f"{rel}:{node.name}")
    assert definitions == ["app/db/errors.py:detect_transient_write_conflict"]


def test_json_payload_variant_has_single_source() -> None:
    """防漂移（P2-2e）：`with_variant(JSONB` 只允许出现在 app/db/types.py 与迁移 helper。"""

    allowed = {"app/db/types.py", "migrations/helpers/dialect.py"}
    offenders = [
        rel for rel, source in _backend_sources("app", "migrations") if "with_variant(JSONB" in source
    ]
    assert set(offenders) <= allowed, f"JSON 双方言别名散落：{sorted(set(offenders) - allowed)}"


def test_write_retry_loop_has_single_definition() -> None:
    """防漂移（CP1b）：写冲突退避重试只在 app/db/retry.py 实现一次。

    `idempotency_service.py` 是**读**重试：不 rollback、结果为 None 也继续重试、
    并用 for-else 兜底再读一次。它与写重试的事务语义不同，且当前没有测试覆盖，
    因此暂列为例外；补齐覆盖后应一并收口，不要以它为模板新增第三套重试。
    """

    allowed = {"app/db/retry.py", "app/services/idempotency_service.py"}
    offenders = [
        rel
        for rel, source in _backend_sources("app")
        if rel not in allowed and "except OperationalError" in source
    ]
    assert offenders == []


def test_write_retry_consumers_use_shared_helper() -> None:
    """防漂移（CP1b）：三个写重试调用点必须走 run_with_write_retry，不得各自手写循环。"""

    expected = {
        "app/ai/page_mutation_executor.py",
        "app/ai/platform_runtime.py",
        "app/services/page_screenshot_job_service.py",
    }
    consumers = {
        rel
        for rel, source in _backend_sources("app")
        if "run_with_write_retry(" in source and rel != "app/db/retry.py"
    }
    assert consumers == expected


def test_claim_functions_must_delegate_cas_timing() -> None:
    """防漂移（CP4）：普通队列的认领时序只在 durable_job_lease_service 实现一次。

    `claim_*` 函数可以自带候选谓词与领域取值，但条件 UPDATE 必须由
    `claim_pending_jobs` / `claim_rows_by_cas` 执行。历史上构建服务自行写过一份
    「读候选 → 结束读事务 → 逐条 CAS」循环，两处会各自演化：漏掉读事务收口会让
    SQLite 直接以写锁失败，漏掉 rowcount 判定则会双跑。判定用 AST 精确识别「直接
    execute 条件 UPDATE」，不用字符串组合近似，避免误伤同样含 pending/running
    字面量的状态机代码。

    `external_task_queue._claim_ready_batch` 是**已核准的例外**，不是漏改：
    1. 认领键是 `batch_id` 业务主键，不是自增 `id`；
    2. 它是「读到实体 → 以该实体的 `lease_generation` 作为 CAS 条件」的**租约围栏**
       协议，认领成功与否取决于上一代 generation，`claim_rows_by_cas` 不表达该语义；
    3. 认领必须与 `AiAgentRequirement` 置 `resolving` 在同一事务内原子完成，且抢锁
       失败时显式 rollback 而非提交。
    共享认领助手不承诺这三点。新增队列若不符合这三条，必须走 `claim_rows_by_cas`，
    不得以它为模板再写一份。
    """

    exempt = {"app/ai/external_task_queue.py"}
    offenders: list[str] = []
    for rel, source in _backend_sources("app"):
        if rel == "app/services/durable_job_lease_service.py" or rel in exempt:
            continue
        for name in _claim_functions_executing_own_cas(source):
            offenders.append(f"{rel}::{name}")
    assert offenders == []


def test_models_should_not_declare_dialect_specific_index_predicates() -> None:
    """防漂移（P2-2f）：model 必须走 db/indexes.partial_index，不得再写 sqlite_where/postgresql_where。"""

    offenders = [
        rel
        for rel, source in _backend_sources("app/models")
        if "sqlite_where=" in source or "postgresql_where=" in source
    ]
    assert offenders == []


def test_claim_drift_helper_detects_direct_cas_execution() -> None:
    """正例对照：认领漂移判定必须真的识别直接 execute 条件 UPDATE，否则门禁会空转。

    上一条码住构建服务手写 claim 的门禁，其有效性完全取决于这个解析函数；没有对照
    用例时，任何把它改宽的修改都会让门禁静默失效。
    """

    hand_written = '''
async def claim_job(self):
    result = await self.session.execute(
        update(ProjectBuildJob).where(ProjectBuildJob.status == "pending").values(status="running")
    )
    return result.rowcount
'''
    delegated = '''
async def claim_job(self):
    def _claim_cas(row):
        return update(ProjectBuildJob).values(status="running")

    rows = await claim_rows_by_cas(self.session, claim_cas=_claim_cas)
    return rows
'''
    assert _claim_functions_executing_own_cas(hand_written) == ["claim_job"]
    assert _claim_functions_executing_own_cas(delegated) == []


def _backend_sources(*subtrees: str):
    """遍历 backend 指定子树源码，返回 (相对 backend 的路径, 源码) 序列。"""

    backend_root = Path(__file__).resolve().parents[2]
    for subtree in subtrees:
        for path in sorted((backend_root / subtree).rglob("*.py")):
            yield path.relative_to(backend_root).as_posix(), path.read_text(encoding="utf-8")


def _claim_functions_executing_own_cas(source: str) -> list[str]:
    """解析源码中的认领函数，返回「自己执行条件 UPDATE」的函数名。

    认领函数按命名约定识别（`claim*` / `_claim*`）。判定标准是函数体内出现
    `await session.execute(update(...))`：构造 UPDATE 并交给共享助手执行是 CP4 的
    正确写法（`claim_rows_by_cas` 的 `claim_cas` 回调就是这种），自己 execute 才是
    重新实现认领时序。
    """

    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        if not node.name.startswith(("claim", "_claim")):
            continue
        if _executes_own_update(node):
            offenders.append(node.name)
    return offenders


def _executes_own_update(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """判断函数体内是否存在对条件 UPDATE 的直接执行。"""

    for node in ast.walk(function_node):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "execute":
            continue
        if not call.args:
            continue
        for sub in ast.walk(call.args[0]):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "update":
                return True
    return False
