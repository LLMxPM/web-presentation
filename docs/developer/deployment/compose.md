# Compose 部署说明

`deploy/` 提供五类部署模板，覆盖 SQLite 轻量版、快速试部署、外部依赖部署、production env 版部署和分角色单机部署。每类模板都启动独立 Renderer；“单容器”仅指轻量版将 Backend、Runtime 和 Gateway 合并在一个平台容器内。现有四类单 Runtime 模板保持原有行为与启动方式不变，Lite 仍为单 Runtime。

官方发布的 Platform、SQLite Lite、Runtime 和 Renderer 镜像同时支持 `linux/amd64` 与 `linux/arm64`。Compose 文件不固定 `platform`，Docker 会按宿主机架构自动选择镜像；需要在本机交叉构建 ARM64 镜像时，应使用已启用 QEMU 的 Buildx 环境。

## 模板

| 文件 | 场景 | 特点 |
| :--- | :--- | :--- |
| `deploy/compose/compose.sqlite-lite.yml` | 个人/小团队轻量部署 | `platform-lite` 内置 Backend、Editor、Runtime 和 Gateway，另有 Renderer；使用 SQLite 与 memory runtime |
| `deploy/compose/compose.with-deps.yml` | 单机试部署 | 启动 PostgreSQL、Redis、platform、runtime 和 renderer |
| `deploy/compose/compose.yml` | 外部依赖简化版 | 启动 platform、runtime 和 renderer；数据库与 Redis 使用外部服务 |
| `deploy/compose/compose.prod.yml` | 生产 env 版 | 拆分迁移、Backend、Runtime、Renderer 和 Gateway，通过 `deploy/.env` 管理变量 |
| `deploy/compose/compose.runtime-roles.yml` | 分角色单机 | `runtime-preview` / `runtime-build` / `runtime-check` 各一实例 + Renderer，每角色显式 CPU/内存 limits 与执行预算；Gateway 只代理预览 |

## SQLite 轻量单容器

```bash
cd deploy
docker compose -f compose/compose.sqlite-lite.yml config
docker compose -f compose/compose.sqlite-lite.yml pull
docker compose -f compose/compose.sqlite-lite.yml up -d
```

默认拉取 `llmxpm/web-presentation:sqlite-lite`，访问 `http://127.0.0.1:8080`。该模式不启动 PostgreSQL 和 Redis，`DATABASE_URL` 指向 `/app/backend/data/web_presentation.db`，`REDIS_URL` 使用 **`memory://lite`（正式运行态适配器）**。`lite-data` volume 同时保存 SQLite 数据库、本地资源、截图、构建产物和 Runtime RSA 私钥。重启后临时预览/构建运行态会丢失，主数据不丢；边界见 [运行态存储适配器](../backend/runtime-state-adapter.md)。

需要从源码验证轻量镜像时，直接在仓库根目录执行构建；`deploy/docker/Dockerfile.lite` 会把仓库原生的 `runtime/` 源码和依赖一起打进单容器镜像。

```bash
docker build -f deploy/docker/Dockerfile.lite -t llmxpm/web-presentation:sqlite-lite .
```

交叉构建 ARM64 轻量镜像时，可执行：

```bash
docker buildx build --platform linux/arm64 -f deploy/docker/Dockerfile.lite -t llmxpm/web-presentation:sqlite-lite-arm64 --load .
```

轻量模式的 `platform-lite` 只支持单实例、单 Backend worker、单 Runtime server，并配套独立 Renderer，不适合多副本或高并发写入。容器重启后短生命周期预览链接、内存锁和内存构建状态会失效，但用户、工作空间、项目、页面、资源和 AI 会话等主数据会保留在 SQLite 文件中。

## 试部署

```bash
cd deploy
docker compose -f compose/compose.with-deps.yml pull
docker compose -f compose/compose.with-deps.yml up -d
```

默认访问 `http://127.0.0.1:8080`。上线前必须修改 compose 顶部注释要求的密码、访问地址和 `AI_SECRET_ENCRYPTION_KEY`。

内置 Redis 默认关闭 AOF，减少低配单机上的持续磁盘写入。该 Redis 只承载短生命周期运行态，不保存平台主数据。

## production env 版

```bash
cp deploy/.env.example deploy/.env
cd deploy
docker compose -f compose/compose.prod.yml config
docker compose -f compose/compose.prod.yml pull
docker compose -f compose/compose.prod.yml up -d
```

production env 版适合把环境变量集中放在 `deploy/.env` 中维护。外部 PostgreSQL 和 Redis 需要提前准备。

## 分角色单机（Runtime 角色）

`deploy/compose/compose.runtime-roles.yml` 把 Runtime 拆成 `runtime-preview`、`runtime-build`、`runtime-check` 三个角色容器（`RUNTIME_ROLE` 分别为 `preview`、`build`、`check`），与 Backend、迁移、Renderer 和 Gateway 组成分角色单机拓扑。启动方式与 production env 版相同，读取 `deploy/.env`；角色差异和资源约束写在模板内。

```bash
cp deploy/.env.example deploy/.env
cd deploy
docker compose -f compose/compose.runtime-roles.yml config
docker compose -f compose/compose.runtime-roles.yml pull
docker compose -f compose/compose.runtime-roles.yml up -d
```

### 拓扑与暴露面

| 服务 | 网络 | 宿主机端口 | 说明 |
| :--- | :--- | :--- | :--- |
| `runtime-preview` | `platform-net`（别名 `runtime`、`runtime-preview`） | 无 | 预览角色；Gateway Nginx 固定代理主机名 `runtime` |
| `runtime-build` | `runtime-jobs-net` | 无 | 构建角色；仅 Backend 可达 |
| `runtime-check` | `runtime-jobs-net` | 无 | 源码检查角色；仅 Backend 可达 |
| `renderer` | `platform-net` | 无 | 截图执行 |
| `backend` | `platform-net` + `runtime-jobs-net`（别名 `backend`） | 无 | 两个网络的唯一交点 |
| `gateway` | `platform-net` | `80` | 唯一公开入口，只代理预览角色 |

`runtime-build` / `runtime-check` 不发布宿主机端口，且不加入 `platform-net`；公开 Gateway 挂在 `platform-net` 上，只能通过主机名 `runtime` 到达 `runtime-preview`，构建与源码检查端点不经公开 Gateway 暴露，只由 Backend 经 `runtime-jobs-net` 调用。浏览器访问关系与下文「访问关系」一致。

### 容器资源约束与执行预算（示例值，需按实测调整）

Docker 容器默认不施加 CPU/内存限制；只把一个 Runtime 拆成三个容器不会自动消除宿主机上的资源争抢。模板为每个角色设置 `deploy.resources.limits`，并同时给出匹配的 Runtime 内部执行预算，两者配套修改才算完成隔离。取值依据：

- CPU limits 取「可同时执行的 Worker 数 + 1 核」，给主进程与事件循环留出余量。
- 内存 limits ≈ `RUNTIME_VITE_TASK_CONCURRENCY × RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB`（V8 老生代堆）+ 等量非堆开销（Buffer、文件页、归档、子进程）+ 主进程余量。`--max-old-space-size` 只限制 V8 老生代堆，不能当作 Worker 或容器的内存上限。
- 下表按每角色 2 个并发 Worker 给出示例值。它们不是承诺值：应结合阶段 0 指标（构建归档阶段峰值 RSS、检查队列年龄、预览事件循环延迟）压测后覆盖，并在调整并发或老生代预算时同步调整 limits。

| 服务 | CPU limits | 内存 limits | 对应执行预算（关键项） |
| :--- | :--- | :--- | :--- |
| `runtime-preview` | 2 | 2Gi | `RUNTIME_VITE_TASK_CONCURRENCY=2`；无构建 Worker 预算（角色门禁后不应有构建/诊断任务） |
| `runtime-build` | 4 | 8Gi | `RUNTIME_VITE_TASK_CONCURRENCY=2`，`RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB=2048`，队列 8 |
| `runtime-check` | 2 | 6Gi | `RUNTIME_VITE_TASK_CONCURRENCY=2`，`RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB=1536`，诊断 Worker 复用并按 RSS 比例回收 |
| `renderer` | 2 | 4Gi | 渲染并发与队列仍由 `deploy/.env` 中 `RENDER_*` 决定 |
| `backend` | 2 | 2Gi | AI 页面与渲染队列仍由 `deploy/.env` 决定 |
| `gateway` | 1 | 512Mi | — |

### 健康检查与依赖顺序

三个角色容器都用 `/__runtime_healthz` 做 healthcheck，探针只看本进程，不依赖 Backend。启动顺序为：`renderer` 与三个 runtime 角色就绪 → `backend-migrate` 成功完成 → `backend` 健康 → `gateway` 健康。Gateway 只依赖 `backend` 与 `runtime-preview`；`runtime-build` / `runtime-check` 由 Backend 按需调用，不进入公开就绪链路。

`RUNTIME_ROLE` 由 Runtime 角色逻辑（规划 T1-1）消费：`preview` 不开放构建与诊断入口，`build` / `check` 只保留对应执行面。模板可先于角色逻辑部署；在角色路由契约完成前，Backend 的 `RUNTIME_BASE_URL` 仍指向 `runtime-preview`，构建与源码检查内部目标按发布顺序逐项切换到 `runtime-build` / `runtime-check`。

### 计算副本扩容（Check/Build 多副本与全链路准入）

按实测瓶颈需要增加 `runtime-build` / `runtime-check` 副本时（规划 T2-3）：

1. 为新副本复制对应角色服务定义，改用独立容器名/别名（如 `runtime-build-2`），保持 `RUNTIME_ROLE` 与执行预算一致；副本只挂 `runtime-jobs-net`，仍不发布宿主机端口。
2. 在 Backend 环境用 `RUNTIME_BUILD_BASE_URLS` / `RUNTIME_CHECK_BASE_URLS` 注册全部副本内网地址（逗号分隔或 JSON 数组）。Backend 按轮询选址；某副本满载（429/503）时自动切换其它空闲副本，全部满载返回稳定错误码 `RUNTIME_CAPACITY_EXCEEDED`（503，可重试）。目标连续失败达到 `RUNTIME_TARGET_FAILURE_THRESHOLD` 后按 `RUNTIME_TARGET_COOLDOWN_SECONDS` 短暂冷却，冷却到期自动恢复。
3. 按「副本数 × 单副本执行预算」上调 `RUNTIME_BUILD_MAX_INFLIGHT` / `RUNTIME_CHECK_MAX_INFLIGHT`，这是 Backend 侧全链路准入上限：在途调用超限立即返回 `RUNTIME_ADMISSION_FULL`（503，可重试），避免 Check 扩容后把 Renderer/Preview 打穿。`preview` 仍保持单副本，不参与多目标选址。

Runtime 本地队列（`RUNTIME_VITE_TASK_*`）仅承担单实例容量保护，不做全局公平；跨副本分摊由上述选址与准入负责。满载与准入拒绝均属可重试容量问题，不应记为业务失败。

## 访问关系

浏览器访问平台 Gateway。Gateway 代理 `/api`、`/public`、`/build-artifacts`、`/preview`、`/media` 到 Backend，并代理 `/runtime/` 到 Runtime。
