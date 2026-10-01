# M04 多副本可靠性与构建/外部交接验收（2026-10-01）

本轮针对架构调整收尾计划中的第一批（M04 多副本可靠性与构建/AI 外部交接）进行了定向测试与验收。代码基于提交 `c4971e3`（已包含 SQLite Alembic 事务接管与 Renderer 400 契约映射），在 Windows 环境通过 `uv run --project backend pytest` 完成了全部 36 项集成测试回归。

## 1. 验证范围与核心场景

### 1.1 构建 Attempt 故障、租约围栏与晚到上传（INV-5）

- **测试文件**：[`backend/tests/integration/test_project_build_job_lease.py`](file:///c:/code/wp/web-presentation/backend/tests/integration/test_project_build_job_lease.py)
- **新增用例**：`test_late_upload_after_success_should_reject_and_preserve_promoted_artifact`
- **核心断言**：
  1. 模拟构建 Attempt 1 超时后被协调器标记失效回收，重新发起 Attempt 2 并成功构建、提升产物（`succeeded` 终态）。
  2. 迟到的 Attempt 1 尝试调用 `upload_build_artifact` 提交产物，触发 INV-5 租约围栏检查。
  3. 系统返回 HTTP 409 `BUILD_JOB_NOT_EXECUTABLE`，拒绝晚到写入。
  4. 检查对象存储：迟到 Attempt 1 上传的临时产物被立即物理清理（`OBJECT_NOT_FOUND`）；
  5. 检查 Job 实体：已成功提升的 Attempt 2 产物（`build_artifact_id`、`build_artifact_path`）和元数据完好无损，未发生任何污染或覆盖。

### 1.2 全局与工作空间并发配额限制与排斥保护

- **测试文件**：[`backend/tests/integration/test_concurrency_quotas.py`](file:///c:/code/wp/web-presentation/backend/tests/integration/test_concurrency_quotas.py)
- **用例覆盖**：
  1. `test_render_workspace_concurrency_limit_enforced`：
     - 单工作空间并发配额设为 1；
     - 两个排队渲染请求并发派发，首个请求成功认领并分配 slot，第二个请求因工作空间额度饱和停留在 `queued`；
     - 首个请求的 attempt 终态并释放 slot 后，再次调度成功派发第二个请求。
  2. `test_render_global_concurrency_limit_enforced`：
     - 全局并发配额设为 1，工作空间配额设为 5；
     - 两个不同工作空间的请求并发派发，首个请求成功派发，第二个跨空间请求因全局额度饱和被拦截；
     - 释放首个请求 slot 后，第二个请求恢复派发并成功分配 worker。
  3. `test_project_build_job_mutex_and_release`：
     - 同一项目已有运行态构建任务（`running`）时，再次发起构建严格返回 HTTP 409 `PROJECT_BUILD_ALREADY_RUNNING`；
     - 当现有任务达到终态（`failed` / `succeeded`）后，互斥释放，允许重新发起新构建。

### 1.3 AI 外部交接与 Batch 一次消费

- **测试文件**：[`backend/tests/integration/test_ai_external_task_queue.py`](file:///c:/code/wp/web-presentation/backend/tests/integration/test_ai_external_task_queue.py)
- **核心断言**：
  1. **双协调器 CAS 竞争**：`test_ready_batch_cas_should_allow_only_one_coordinator` 模拟两个协调器实例并发调用 `_claim_ready_batch` 认领同一 ready Batch，严格只有一个协调器认领成功，Batch 变更为 `resuming`，关联 Requirement 置为 `resolving`，杜绝重复续跑。
  2. **Batch 一次消费与结果清空**：`test_real_continuation_handoff_should_resolve_old_requirement_before_next_batch` 验证模型成功消费任务后，旧 Requirement 终态为 `resolved`，旧 Task 的完整 `result_json` 彻底清空为 `None`，并记录 `result_consumed_at` 时间戳，仅保留轻量元数据。
  3. **失败保留结果**：`test_failed_continuation_should_keep_full_task_result` 验证续跑失败时，Batch 置为 `failed`，保留完整 `result_json` 以供排障或重试，不发生数据丢失。
  4. **心跳与租约过期防护**：`test_batch_heartbeat_loss_should_signal_continuation_cancel` 与 `test_expired_resuming_batch_should_restore_ready_and_requirement_pending` 验证租约过期时安全回滚为 `ready`，避免任务挂死。

---

## 2. 测试执行记录

执行命令：
```powershell
uv run --project backend pytest backend/tests/integration/test_project_build_job_lease.py backend/tests/integration/test_concurrency_quotas.py backend/tests/integration/test_ai_external_task_queue.py
```

执行结果：
```text
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\code\wp\web-presentation\backend
configfile: pyproject.toml
plugins: anyio-4.15.1, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 36 items

backend\tests\integration\test_project_build_job_lease.py .............. [ 38%]
..                                                                       [ 44%]
backend\tests\integration\test_concurrency_quotas.py ...                 [ 52%]
backend\tests\integration\test_ai_external_task_queue.py ............... [ 94%]
..                                                                       [100%]

============================= 36 passed in 29.92s =============================
```

## 3. 验收结论

1. **M04 门禁关闭**：构建 Attempt 晚到上传防护与物理清理、全局/工作空间并发配额拦截释放、以及统一 AI 外部 Batch 的 CAS 竞争与一次消费语义均已达成计划要求，具备完整的行为证据。
2. **计划状态推进**：第一批（多副本可靠性与构建/AI 外部交接）完成，可进入第二批（M02 隔离与 M07 恢复）或视计划推进后续环节。
