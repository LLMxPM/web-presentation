> **归档说明（2026-09-29）**：本文已由新一轮静态评估与计划接替，不再作为现行状态或执行入口。原位置：`docs/temp/plans/test-machine-runbook-2026-09-29.md`。历史完成标记、测试结果、发布状态和建议均只代表当时记录；本轮没有重新验证。现行入口：[架构评估](../architecture-assessment-2026-09-30.md) · [改进与下一轮验证计划](../plans/architecture-improvement-plan-2026-09-29.md)。

<!-- 文件功能：测试机环境准备与待执行验收清单（WS-D / C9 / IMG0），本地代码收口后的下一步。 -->
# 测试机准备与验收清单（2026-09-29）

> **状态**：准备材料 / 未开跑。本地可做项（G7/G1/G2/G3密钥/G5/G6/IMG1/死物/分层门禁）已落地后编写。  
> **用途**：拿到测试机后按本清单执行，不重复设计。完成后把结果回填 [`remaining-work-2026-09-28.md`](./remaining-work-2026-09-28.md) 对应工作项。

---

## 0. 需要什么机器

| 用途 | 最低配置 | 数量 | 对应工作项 |
| :--- | :--- | :--- | :--- |
| Lite 容量基线 | **2C4G**，Docker，可跑 `sqlite-lite` | 1 | WS-D1–D5 |
| 容器内 Chromium | 任意可 Docker 构建 `renderer/Dockerfile` 的机器 | 可与上合并 | IMG0 |
| 跨副本演练 | 4C8G+ 或 2×2C4G；能起 2 Backend / 2 Runtime / 2 Renderer | 1–2 | WS-C C9 |
| 发布预演 | 可推 registry 的 CI 或构建机 | 按需 | IMG2–IMG4 |

**本轮优先**：一台 2C4G 即可先跑 **IMG0 + WS-D**；C9 可后置。

---

## 1. IMG0 · 容器内 root 启动 Chromium（阻塞级，0.5 天）

**目的**：验证 `chromium.launch(headless=True)` 无 `--no-sandbox` 在 root 容器能否稳定启动。这是 lite 合并与 renderer 首发的前置。

```powershell
# 在仓库根
docker build -f renderer/Dockerfile -t wp-renderer:img0 .
docker run --rm -p 7400:7400 --name img0-renderer `
  -e RENDER_SERVICE_CREDENTIAL=img0-test-credential `
  wp-renderer:img0

# 另开终端：健康检查 + 真实截图（走 wp_renderer 自己的启动路径，不得代传 --no-sandbox）
curl -fsS http://127.0.0.1:7400/readyz
# 用现有 test:render-e2e 的最小断言或 scripts/contracts/check-image-startup.py 的 renderer 分支
# 但去掉测试脚本里的 --no-sandbox，确认 executor.py 默认路径能起浏览器
```

**判定**：

| 结果 | 后续 |
| :--- | :--- |
| 能启动并出图 | 记录日志；IMG5+ 可继续；写入 WS-G5 证据 |
| 不能启动 | 定稿 `--no-sandbox` 或非 root `USER`；同步 compose/Dockerfile 与风险文档 |

**记录**：镜像 digest、`/readyz` 输出、一次 PNG 产物路径、失败时完整 stderr。

---

## 2. WS-D · Lite 2C4G 基线（1–2 天）

### 2.1 准备

```powershell
# 生成强密钥（启动会拒绝占位值）
python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
python -c "import secrets; print(secrets.token_urlsafe(16))"

# 按 docs/user/quick-deployment/docker.md 起 sqlite-lite
# 打开写路径打点（仅采集期）
# 环境变量：DATABASE_WRITE_PATH_METRICS_ENABLED=true
```

### 2.2 D1 空闲 + 混合负载两轮

| 轮次 | 操作 | 采集 |
| :--- | :--- | :--- |
| 空闲 | 启动后静置 10 分钟 | `/metrics/db-write`、`/metrics/job-queues`、`/metrics/runtime-state`、容器 RSS |
| 混合 | 2–3 会话并发：预览刷新、截图、构建、AI 页改 | 同上 + `docker stats` 每 30s |

**必须写成文的数字**：锁等待/写冲突、队列年龄 P50/P95、SQL P50/P95、RSS 峰值、是否 OOM。

### 2.3 D2 busy_timeout 风暴

并发写压测（多会话同时保存页面/触发截图），确认写路径可解释、可恢复；记录 `busy_timeouts`。

### 2.4 D3 成功构建产物可下载

Lite 真实容器内：项目构建成功 → 下载 zip → 校验入口文件存在。**不要以按钮可见代替。**

### 2.5 D4/D5

- D4：记录机型；换机只需重跑 §2.2 命令清单。
- D5：两阶段校验（编译 vs 视觉）耗时拆分各一轮。

**回填**：`remaining-work` WS-D 表；Lite 规模是否仍维持「5–10 人 / 并发 3」目标（未过 D2 仍不是 SLA）。

---

## 3. WS-C C9 · 跨副本演练（2–3 天，可后置）

**拓扑**：2× Backend、2× Runtime preview+build、2× Renderer；静态 compose 复制即可（不要求动态发现）。

| 步骤 | 断言 |
| :--- | :--- |
| 双预览交叉请求 | 强制跨副本子请求，预览可用 |
| 双构建检查 | attempt 围栏：迟到上传不得提升旧产物 |
| 双 Renderer | 单 Worker 占用唯一；额度不因双协调器超限（对照 WS-C RenderQuota） |
| 重启 Backend-A | **不得**终态化 Backend-B 活跃 Run（`process_owner`） |
| 摘流/缩容 | `check_render_worker_removal` 可用；无悬挂租约 |
| 版本指纹 | 故意错 `X-Expected-Runtime-Version-Fingerprint` → 409 |

**未过则**：compose 继续标「单副本」；禁止对外宣称多副本可用。

---

## 4. 开跑前检查清单

- [ ] 测试机能拉取 `llmxpm/web-presentation:sqlite-lite` 或本地构建
- [ ] 已生成强 `AI_SECRET_ENCRYPTION_KEY` / `DEFAULT_ADMIN_PASSWORD`（占位会被启动拒绝）
- [ ] 仓库工作区干净或已知改动；基线 commit 记在结果里
- [ ] `DATABASE_WRITE_PATH_METRICS_ENABLED=true` 仅用于采集
- [ ] 结果目录：`docs/temp/runs/<date>-test-machine/`（原始日志 + 摘要）

---

## 5. 本地已收口、测试机不必重做

- WS-G7 Run 文案区分、WS-G1/G5/G6/IMG1 文档、G3 占位密钥拒绝、G2 `/metrics/job-queues`
- 死 scope/死列清理、`test_layering_gates` 分层门禁
- WS-B / WS-A / WS-E / WS-C 代码项（C9 除外）
