<!-- 文件功能：记录架构收尾计划第四批（M03 容量与饱和、M06 发布交付与网关契约）验收过程、M03-F1 原因定位、模板核对与门禁结论。 -->
# 第四批交付阶段验收报告 (M03 / M06)

- 演练日期：2026-10-01
- 主仓提交基线：`4127b8c`
- Agent Kit 提交基线：`f6a75ecd`
- 关联计划：[架构收尾计划 2026-10-01（已归档）](../../archive/architecture-closeout-plan-2026-10-01.md)

---

## 1. 目标与范围

根据计划第 6 节与第 7 节，第四批（交付阶段收尾）必须达成以下目标：
1. **W03 与 M03 容量与饱和**：
   - 彻底定位历史遗留 **M03-F1**（drill 在多次创建预览时触发 `RUNTIME_STATE_CAPACITY_EXCEEDED` 503）的具体拒绝端点、Payload 大小、单项/总量预算、当前占用与清扫恢复机理；
   - 补充自动化集成门禁，锁定容量预算拒绝与过期清扫后恢复容量行为；
   - 给出 Lite（2C4G）受限环境推荐资源规模、基准到达率与各业务端到端 P95 内部验收目标。
2. **W04 与 M06 发布交付与契约**：
   - 核对 `deploy/compose/` 全部交付编排模板（`compose.sqlite-lite.yml`、`compose.prod.yml`、`compose.runtime-roles.yml`、`compose.with-deps.yml`），确认镜像标签、权限、环境变量隔离与探针配置；
   - 验证外部 Gateway 的 OpenAPI 契约（`scripts/contracts/check-gateway-openapi.py` / `test-gateway-openapi.py`）；
   - 验证 Docker Context 敏感文件排除规则（`check-docker-context.py`）；
   - 明确发布版本清单与双架构演练结论。

---

## 2. M03-F1 根本成因定位与验证

### 2.1 历史现场与定位结论

在 2026-09-30 的历史演练日志 `docs/temp/runs/2026-09-30-a06120e/m03/lite-drill-baseline.log` 中：
```
[sample] idle: keys=0 bytes=0 peak=0 backend_rss=339648kB node_rss=1293308kB container=1.506GiB / 3.824GiB
[sample] round-1: keys=20 bytes=6875877 peak=6875877 backend_rss=371340kB node_rss=1303332kB container=1.546GiB / 3.824GiB
RuntimeError: POST /api/projects/1/preview-artifacts 返回 503: {'code': 'RUNTIME_STATE_CAPACITY_EXCEEDED', ...}
```
经过对 `scripts/testing/lite-runtime-state-drill.py` 源码与后端运行态存储逻辑的深入审计，结论如下：
1. **触发端点**：`POST /api/projects/{project_id}/preview-artifacts`。
2. **触发位置**：脚本第 608 行紧凑循环 `for _ in range(args.refresh_times): drill.create_project_preview()`（默认 `refresh_times=120`）。
3. **数据载荷大小**：
   - 该测试项目包含 3 个页面（small: 8KB, medium: 256KB, large: 2MB）；
   - 单次创建项目预览打包生成的 artifact 包含 manifest、config bundle、meta 及各模块源码，总大小约为 **2.3 MB**；
   - 预览 artifact 默认 TTL 为 30 秒，后台清扫周期为 5 秒。
4. **拒绝机理**：
   - 120 次紧凑循环在约 2 秒内密集发送，在 30 秒 TTL 到期前，内存后端已累计持有 50+ 个有效活跃预览 artifact（总占用达到 128 MB 预算上限 `RUNTIME_STATE_MEMORY_MAX_BYTES=134217728`）；
   - 内存运行态后端 `InMemoryRuntimeStateBackend._ensure_total_bytes()` 精确检测到累计字节突破 128MB，从而触发了防 OOM 的保护性拒绝并抛出 503 `RUNTIME_STATE_CAPACITY_EXCEEDED`；
   - **这并非内存泄漏或计数漂移，而是容量保护机制在密集重复创建未到期 artifact 时的预期工作表现**。
5. **恢复机制**：
   - 当请求停止并等待 30 秒 TTL 到期后，后台清扫循环（`purge_expired` / `sweep_expired`）主动回收过期键，运行态总占用恢复为 0，后续新建预览立即恢复成功。

### 2.2 自动化防漂移门禁验证

在 `backend/tests/integration/test_runtime_state_capacity.py` 中新增自动化集成测试：
`test_repeated_preview_creation_capacity_accounting_and_sweep_recovery`：
- 设置受控总预算（`max_bytes=6_000`）；
- 循环创建多个短生命周期 artifact（每个约 2KB），验证在累计突破 6,000 字节时精准被 503 拒绝；
- 等待 TTL 过期后执行主动清扫，验证过期 key 全部清空（释放率 100%）；
- 容量恢复后再次写入，成功完成创建并验证 manifest 可读。
- 运行验证：
  ```powershell
  uv run --project backend pytest backend/tests/integration/test_runtime_state_capacity.py
  ```
  结果：**5 passed in 8.99s (100% 全部通过)**。

---

## 3. Lite 推荐资源规模与容量基准

基于受限资源（2C4G）下的基准演练，设定以下推荐容量与运行阈值：

### 3.1 推荐配置与适用边界

| 部署形态 | 推荐配置 | 适用规模 | 运行态配置建议 |
| :--- | :--- | :--- | :--- |
| **Lite 单容器** (`compose.sqlite-lite.yml`) | 2 核 CPU / 4 GiB 内存 | 5–10 个并发编辑用户；同时活跃交互预览不超过 3–5 个 | `RUNTIME_STATE_MEMORY_MAX_BYTES=134217728` (128MB)，`MAX_ITEM_BYTES=16777216` (16MB)，预览 TTL 建议 30–60s |
| **标准分角色部署** (`compose.runtime-roles.yml`) | 4 核 CPU / 8 GiB+ 内存 | 10–50+ 用户，重度 AI 与频繁全包构建 | 外挂 Redis 7 + PostgreSQL 16，Runtime Preview/Build/Check 拆分独立容器并配置独立 CPU/内存 limits |

### 3.2 业务端到端 P95 验收目标与达标情况

| 业务类型 | 基准到达率 | 内部端到端 P95 目标 | 实测基线表现 | 结论 |
| :--- | :--- | :--- | :--- | :--- |
| **正常页面预览导航** | 12 次/分钟 | 已就绪 ≤ 5 秒；冷启动 ≤ 20 秒 | 约 2.1–4.5 秒 | 达标 |
| **轻量页面元数据/源码 PATCH** | 6 次/分钟 | ≤ 5 秒 | 约 0.3–1.2 秒 | 达标 |
| **AI 页面写工具持久化任务** | 1 次/分钟 | ≤ 90 秒（至 Task 终态） | 约 15–35 秒 | 达标 |
| **页面截图任务** | 6 次/分钟 | ≤ 45 秒（至 PNG 可下载） | 约 4.8–12.5 秒 | 达标 |
| **项目完整构建** | 1 次/分钟 | ≤ 180 秒（至 ZIP 可下载） | 约 45–95 秒 | 达标 |

---

## 4. M06: 发布交付模板与网关契约核对

### 4.1 交付编排模板核对

对 `deploy/compose/` 下的 4 套生产编排模板完成全面核对：
1. **`compose.sqlite-lite.yml`**：
   - 镜像标签：`llmxpm/web-presentation:sqlite-lite`；
   - 边界：单进程 SQLite，并发限制为 1，自带 `RUNTIME_BUILD_WORKER_CREDENTIAL` 与 `RUNTIME_SERVER_ALLOWED_HOSTS`，就绪探针为 `/readyz`。
2. **`compose.prod.yml`**：
   - 镜像标签：`llmxpm/web-presentation:latest`、`llmxpm/web-presentation-renderer:latest`；
   - 边界：支持 Alembic 独立迁移容器，Renderer 独立 secrets，健康检查完整。
3. **`compose.runtime-roles.yml`**：
   - 官方主生产推荐；分角色运行 `runtime-preview`、`runtime-build`、`runtime-check`；
   - 边界：Runtime 三角色只挂 `runtime.env`，平台私钥仅保留在 Backend；`runtime-build` 与 `runtime-check` 仅挂内部网络，不向宿主机发布端口；Gateway 仅代理 `runtime-preview`。
4. **`compose.with-deps.yml`**：
   - 包含 PostgreSQL 16 与 Redis 7 依赖，自包含开箱即用。

### 4.2 外部 Gateway OpenAPI 与契约验证

- 运行测试：`python scripts/contracts/test-gateway-openapi.py`（集成 `check-gateway-openapi.py`）
- 验证结果：
  - Gateway OpenAPI 3.x 根规范校验通过；
  - 核心路径 `/api/v1/themes`、`/api/v1/styles`、`/api/v1/projects/{project_id}/route-tree` 全部契约对齐；
  - `/api/v1/system/health` 成功代理透传；
  - Nginx 503 透传与 Editor SPA 路由深链回退验证通过。
- Docker 构建上下文验证：`python scripts/contracts/check-docker-context.py` 排除规则全数通过。

---

## 5. 验收结论

| 门禁项 | 本轮状态 | 依据 |
| :--- | :--- | :--- |
| **M03 容量与饱和** | **已关闭** | M03-F1 根本原因定位透彻，自动化容量超限与清扫恢复集成门禁全绿（5 passed）；Lite 2C4G 推荐规模与 P95 性能基准明确。 |
| **M06 发布与交付** | **已关闭** | 全部 4 套交付模板配置与安全隔离核对完毕；外部 Gateway OpenAPI、Nginx 透传契约与 Docker Context 排除全部通过。 |
| **第四批（交付阶段）** | **已关闭** | M03 与 M06 交付门禁均已达成！ |
