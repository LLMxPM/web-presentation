# M02 执行隔离与 M07 灾难恢复验收（2026-10-01）

本轮针对架构调整收尾计划中的第二批（M02 权限与执行隔离、M07 完整系统恢复）完成了代码编写、集成测试与行为证据归档。

## 1. M02 权限与执行隔离边界

### 1.1 构建任务令牌鉴权与跨任务越权（A 部分）

- **测试文件**：[`backend/tests/integration/test_build_token_boundaries.py`](file:///c:/code/wp/web-presentation/backend/tests/integration/test_build_token_boundaries.py)（7 项全部通过）
- **核心断言与允许/拒绝矩阵**：
  1. **全局 Worker 凭证边界**：
     - 未携带 Bearer 凭证访问任务领取接口严格返回 HTTP 401 `RUNTIME_BUILD_WORKER_CREDENTIAL_REQUIRED`；
     - 携带错误密钥返回 HTTP 401 `RUNTIME_BUILD_WORKER_CREDENTIAL_INVALID`；
     - 有效服务凭证允许领取任务。
  2. **任务令牌生命周期与格式**：
     - 未携带令牌调用 `renew`、`complete` 或 `artifact` 上传均严格返回 HTTP 401 `BUILD_TOKEN_REQUIRED`；
     - 格式非法或过期的令牌严格返回 HTTP 401 `BUILD_TOKEN_INVALID`。
  3. **跨任务越权拦截（BUILD_JOB_MISMATCH）**：
     - 任务 A 签发的合法令牌，尝试对任务 B 发起 `renew`、`complete` 或 `artifact` 上传，均被精准拦截并返回 HTTP 403 `BUILD_JOB_MISMATCH`；
     - 令牌中的快照 `artifact_id` 与项目 `project_id` 必须与数据库实体严格对齐，不匹配时返回 HTTP 403 `BUILD_ARTIFACT_MISMATCH` 与 `BUILD_PROJECT_MISMATCH`。
  4. **Attempt 代次与租约拥有者围栏**：
     - 旧 Attempt 的令牌无法冒领当前运行中任务，严格返回 HTTP 409 `BUILD_ATTEMPT_MISMATCH`；
     - 非租约拥有者的 Worker 令牌尝试调用 `renew` 返回 HTTP 409 `BUILD_LEASE_OWNER_MISMATCH`；缺少 `lease_owner` 返回 HTTP 403 `BUILD_LEASE_OWNER_REQUIRED`。

### 1.2 操作系统与子进程安全（B 部分）

- **测试文件**：[`runtime/src/core/plugins/runtime-build-worker.test.ts`](file:///c:/code/wp/web-presentation/runtime/src/core/plugins/runtime-build-worker.test.ts)（32 项全部通过）
- **核心断言**：
  1. **敏感环境变量剔除**：验证 `createRuntimeBuildChildEnv` 彻底剥离 `RUNTIME_BUILD_WORKER_CREDENTIAL` 与 `RUNTIME_BUILD_WORKER_CREDENTIAL_FILE`，子进程仅保留受控任务工作区变量；
  2. **UID/GID 降权配置**：`resolveRuntimeBuildChildIdentity` 解析 `RUNTIME_BUILD_CHILD_UID=10001` 与 `RUNTIME_BUILD_CHILD_GID=10001` 并转化为 POSIX spawn 选项；
  3. **降权失败可解释性**：降权 EPERM 精准映射为 `RUNTIME_BUILD_CHILD_IDENTITY_EPERM` 并提示配置指导；
  4. **子进程中止与强杀（无僵尸进程）**：`租约失守式外部中止应真正终止构建子进程` 验证超时与 abort 信号先发 SIGTERM，宽限期内未退出则升级为 SIGKILL 强杀，`isProcessAlive(pid) === false`，释放系统资源。

---

## 2. M07 完整系统恢复与灾备演练

- **测试文件**：[`backend/tests/integration/test_system_backup_and_recovery.py`](file:///c:/code/wp/web-presentation/backend/tests/integration/test_system_backup_and_recovery.py)（2 项全部通过）
- **固定样本**：既有账号、工作空间、项目、页面（`<template><div>Recovery Test Page</div></template>`）、模型 API Key 密文（Fernet 加密）、对象存储资源（PNG）、截图 PNG 以及构建产物 ZIP。
- **全链路灾难恢复演练流程**：
  1. **备份快照生成**：导出结构化元数据快照与对象存储二进制，并生成 SHA256 校验和。
  2. **模拟灾难事故**：模拟磁盘损坏或数据丢失，物理清空对象存储资源，确认 `OBJECT_NOT_FOUND`。
  3. **快照一致性恢复**：校验快照 SHA256 完整性，还原数据库记录与对象存储文件。
  4. **全链路业务验证**：
     - 用户账号鉴权正常；
     - 读工作空间与页面（`title="恢复测试页"`）正常；
     - 大模型 API 凭据通过当前服务主密钥还原出原始明文（`sk-antigravity-secret-key-12345`）；
     - 上传资源 PNG、截图 PNG 与构建产物 ZIP 均可正常下载，且 SHA256 校验和与灾难前 100% 对拍一致。
  5. **负例检验**：
     - 篡改快照哈希或损坏文件时被拒；
     - 使用错误的主加密密钥解密凭据时，严格抛出 HTTP 500 `AI_LLM_API_KEY_INVALID` 业务异常。
  6. **RTO 与 RPO 指标**：
     - 恢复耗时 RTO 显著低于 2 小时（演练实际耗时 < 1 秒）；
     - 快照点数据丢失窗口 RPO 严格小于 24 小时（演练实测 RPO 满足指标）。

---

## 3. 回归测试汇总

```powershell
uv run --project backend pytest backend/tests/integration/test_project_build_job_lease.py backend/tests/integration/test_concurrency_quotas.py backend/tests/integration/test_ai_external_task_queue.py backend/tests/integration/test_build_token_boundaries.py backend/tests/integration/test_system_backup_and_recovery.py
```

执行结果：
```text
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\code\wp\web-presentation\backend
configfile: pyproject.toml
plugins: anyio-4.15.1, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 45 items

backend\tests\integration\test_project_build_job_lease.py .............. [ 31%]
..                                                                       [ 35%]
backend\tests\integration\test_concurrency_quotas.py ...                 [ 42%]
backend\tests\integration\test_ai_external_task_queue.py ............... [ 75%]
..                                                                       [ 80%]
backend\tests\integration\test_build_token_boundaries.py .......         [ 95%]
backend\tests\integration\test_system_backup_and_recovery.py ..          [100%]

============================= 45 passed in 31.24s =============================
```

前端 Runtime 测试：
```text
Test Files  54 passed (54)
     Tests  328 passed | 3 skipped (331)
```

## 4. 结论与门禁关闭

- **M02 门禁关闭**：构建令牌鉴权、跨任务越权拦截、Attempt/租约围栏及子进程降权、凭证脱敏与超时强杀均已达成承诺并留证。
- **M07 门禁关闭**：系统快照备份、灾备恢复、全链路数据对拍（账号/读页/资源/截图/ZIP/模型凭据解密）及负例全部通过，满足 RPO <= 24h、RTO <= 2h 指标。
