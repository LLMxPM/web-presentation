# 部署环境变量

production env 版通过 `deploy/.env` 管理环境变量，模板来自 `deploy/.env.example`。分角色单机版的 Backend 也读取该文件，Runtime 三角色只读取由 `deploy/runtime.env.example` 复制的 `deploy/runtime.env`；平台密钥只放在 Backend 的 `deploy/.env`。SQLite 轻量单容器版（`compose.sqlite-lite.yml`）不读取这些文件，支持零配置启动或在 compose 文件内覆盖变量。

## 对外访问

| 变量 | 说明 |
| :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | 平台对外访问地址 |
| `RUNTIME_PUBLIC_BASE_URL` | Runtime 对浏览器暴露的访问地址，同域部署通常为平台地址追加 `/runtime` |
| `CORS_ORIGINS` | 允许访问 Backend 的前端源 |
| `SESSION_SECURE` | HTTPS 部署应设为 `true` |
| `APP_TIMEZONE` | 业务时区，默认 `Asia/Shanghai`；Editor 启动时自动读取，无需重建前端 |

数据库与接口统一使用 UTC，历史无时区值直接补 UTC。业务时区只影响展示和业务日期生成，详见[时间存储与展示](../../developer/backend/time-handling.md)。

## 数据与缓存

| 变量 | 说明 |
| :--- | :--- |
| `DATABASE_URL` | 主数据库连接串；常规部署使用 PostgreSQL，SQLite 轻量模式使用 `sqlite+aiosqlite:////app/backend/data/web_presentation.db` |
| `REDIS_URL` | 运行态存储连接串。常规部署使用 `redis://…`；SQLite 轻量模式**正式**使用 `memory://lite`（进程内适配器） |
| `REDIS_KEY_PREFIX` | Redis 或 `memory://` runtime key 前缀，建议同一运行态多环境隔离 |
| `TIKTOKEN_CACHE_DIR` | tiktoken 词表缓存目录。交付镜像已固定为 `/app/.cache/tiktoken` 并在构建期预置 `cl100k_base`，离线/气隙启动无需出网；覆盖该变量需自行保证缓存文件已存在 |

SQLite 轻量模式不依赖外部 PostgreSQL/Redis。`memory://` 是**受支持的运行态适配器**，与真实 Redis 同契约、不同边界：只保存在当前 Backend 进程内，容器重启后短生命周期预览 artifact、锁和构建运行态会失效；主数据仍保存在 SQLite 文件中。能力矩阵、重启语义与非目标见 [运行态存储适配器](../../developer/backend/runtime-state-adapter.md)。

## 默认管理员

| 变量 | 说明 |
| :--- | :--- |
| `DEFAULT_ADMIN_USERNAME` | 首次启动时使用的默认管理员账号 |
| `DEFAULT_ADMIN_PASSWORD` | 默认管理员密码，生产环境必须替换 |
| `DEFAULT_ADMIN_DISPLAY_NAME` | 默认管理员展示名 |

## AI 配置

| 变量 | 说明 |
| :--- | :--- |
| `AI_ENABLED` | 是否启用 AI 能力，默认 `true` |
| `AI_SECRET_ENCRYPTION_KEY` | 加密用户模型凭证的 Fernet 密钥，必须长期保存并进备份集 |

`AI_SECRET_ENCRYPTION_KEY` 必须是 32 字节随机值的 URL-safe base64 编码，通常长度为 44 个字符并以 `=` 结尾。直接更换该值会导致已有用户模型凭证无法解密；需要更换时请参见 [AI 凭证密钥轮换与迁移指南](../../developer/backend/ai-secret-rotation.md) 进行平滑重密迁移。

## 远程渲染服务

| 变量 | 说明 |
| :--- | :--- |
| `RENDER_WORKERS_CONFIG` | 受信 Renderer Worker 地址 JSON 数组；每个条目含 `worker_id` 与 `base_url` |
| `RENDER_SERVICE_CREDENTIAL_FILE` | Backend/Renderer 共享服务密钥文件路径；与 `RENDER_SERVICE_CREDENTIAL` 二选一，禁止占位符与空文件 |
| `RENDER_SERVICE_CREDENTIAL` | 共享服务密钥明文（不推荐生产使用；优先 secret 文件） |
| `RENDER_PROFILE_DIGEST` | 当前发布要求的渲染环境指纹；与 Renderer 实际 profile 不一致时拒绝执行 |

部署 compose 使用 Docker secrets：启动前必须创建 `deploy/secrets/render_service_credential`（强随机共享密钥，Backend 与 Renderer 一致）。示例：

```powershell
mkdir deploy/secrets
openssl rand -base64 48 | Out-File -Encoding ascii deploy/secrets/render_service_credential
```

## Runtime 内部通信

| 变量 | 说明 |
| :--- | :--- |
| `RUNTIME_BASE_URL` | Backend 调用 Runtime 的内网地址 |
| `RUNTIME_PREVIEW/CHECK_BASE_URL` | 分角色部署时按职责覆盖的内网目标；留空回退 `RUNTIME_BASE_URL`。构建不在这里配置：Runtime Build Worker 主动向 Backend 领取任务 |
| `RUNTIME_BUILD_WORKER_CREDENTIAL` / `RUNTIME_BUILD_WORKER_CREDENTIAL_FILE` | Backend 与 `runtime-build` 共用的领取凭证，两侧必须一致；secret 文件要求 `0400`/`0600`。未配置时 claim API fail-closed、Worker 不启动，构建任务停在 `pending`；构建不存在其它执行入口 |

## 签名身份与多 Backend

| 变量 | 说明 |
| :--- | :--- |
| `RUNTIME_RSA_PRIVATE_KEY` | RS256 签名私钥 PEM 文本；不推荐长期写在 env 文件 |
| `RUNTIME_RSA_PRIVATE_KEY_FILE` | RS256 签名私钥文件路径（共享路径 / secret 挂载）；多 Backend 推荐 |
| `RUNTIME_RSA_KEY_ID` | 当前签名 `kid`，默认 `default-key-1` |
| `RUNTIME_RSA_PREVIOUS_KEYS` | 轮换期旧钥 JSON 数组，每项 `{"kid", "private_key_file"}` 或 `{"kid", "private_key"}`；仅验签与 JWKS 公布 |
| `BACKEND_MULTI_INSTANCE` | 声明多 Backend 副本部署，默认 `false`；开启后启动期强制共享密钥与对象存储前提 |

私钥读取顺序：`RUNTIME_RSA_PRIVATE_KEY` → `RUNTIME_RSA_PRIVATE_KEY_FILE` → 旧版 `data/runtime_rsa_key.pem` → 单实例自动生成。多 Backend 副本必须共享同一签名私钥与对象存储；密钥轮换时旧票据在自身 TTL 内仍有效，移出旧钥后立即失效。完整前提、轮换步骤与旧票据语义见 [多 Backend 与密钥一致性](./multi-backend.md)。

## 日志

| 变量 | 说明 |
| :--- | :--- |
| `LOG_LEVEL` / `LOG_FORMAT` | Backend 业务日志等级与格式 |

Gateway Nginx 访问日志在平台镜像配置中默认关闭；错误日志仍输出到标准错误。

## 资源存储

| 变量 | 说明 |
| :--- | :--- |
| `ASSET_STORAGE_DRIVER` | `local` 或 `s3` |
| `S3_ENDPOINT_URL` | S3 兼容服务地址 |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | S3 访问凭证 |
| `S3_BUCKET` | 私有资源 bucket |
| `S3_PUBLIC_BUCKET` | 可选公开字体 bucket |
| `S3_REGION` | S3 区域，例如 `us-east-1` |
| `S3_PUBLIC_BASE_URL` | 公开资源访问地址 |

---

## 隐式调优参数（类 C：内置常量与默认值）

以下参数已从常规部署模板（`.env.example`）中精简移除，由系统代码默认值内聚管理（定义于 `backend/app/core/config.py` 中的 `AppSettings`），在绝大多数生产与 Lite 环境中无需显式配置。当处于极端负载、特殊性能调优或定制拓扑场景时，仍可通过环境变量显式覆盖：

### 1. 内部通信 Audience 契约

已收敛为代码常量契约，通常无需修改：
- `RUNTIME_SERVICE_TOKEN_AUDIENCE`：Backend 调用 Runtime 内部服务令牌 Audience，默认 `runtime-backend`。
- `RUNTIME_PREVIEW_TOKEN_AUDIENCE`：预览令牌 Audience，默认 `runtime-preview`。
- `RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE`：编译诊断令牌 Audience，默认 `runtime-diagnostics`。
- `AI_AGENT_OS_ID`：系统内部智能体标识常量。

### 2. 调度租约与心跳控制

- `DURABLE_JOB_LEASE_SECONDS`：通用持久化任务跨进程租约时长，默认 `300` 秒。
- `DURABLE_JOB_HEARTBEAT_SECONDS`：通用持久化任务心跳续租周期，默认 `30` 秒。
- `AI_PAGE_MUTATION_CONCURRENCY`：AI 页面生成持久化 Worker 并发数，SQLite Lite 默认 `1`，常规部署默认 `2`。
- `AI_PAGE_MUTATION_MAX_ACTIVE_JOBS`：全局活跃与等待的页面变更任务队列上限，Lite 默认 `16`，常规部署默认 `64`。
- `AI_PAGE_MUTATION_MAX_BATCH_SIZE`：页面变更批处理上限，默认 `16`。
- `AI_PAGE_MUTATION_POLL_INTERVAL_SECONDS`：页面变更任务轮询间隔，默认 `0.5` 秒。

### 3. AI 运行态超时与执行管理

- `AI_AGENT_STREAM_IDLE_TIMEOUT_SECONDS`：模型请求流连续无事件时的超时中断阈值，默认 `180` 秒。
- `AI_AGENT_TOOL_STREAM_IDLE_TIMEOUT_SECONDS`：工具执行流连续无事件时的超时阈值，默认 `600` 秒。
- `AI_EXTERNAL_TASK_ENQUEUE_TIMEOUT_SECONDS`：外部异步任务入队超时，默认 `30` 秒。
- `AI_RUN_OWNER_TTL_SECONDS`：AI Run 进程属主租约 TTL，默认 `90` 秒。
- `AI_RUN_OWNER_HEARTBEAT_SECONDS`：AI Run 属主心跳刷新间隔，默认 `10` 秒。
- `AI_RUN_OWNER_SWEEP_SECONDS`：属主收敛与孤儿清理间隔，默认 `10` 秒。

### 4. 远程渲染细粒度并发与队列

- `RENDER_GLOBAL_CONCURRENCY`：平台全局活动渲染请求上限，默认 `2`（Lite 单机固定为 `1`）。
- `RENDER_WORKSPACE_CONCURRENCY`：单工作空间活动渲染上限，默认 `1`。
- `RENDER_QUEUE_SIZE`：平台全局渲染等待队列上限，默认 `64`。
- `RENDER_WORKSPACE_QUEUE_SIZE`：单工作空间等待队列上限，默认 `16`。
- `RENDER_REQUEST_TIMEOUT_SECONDS`：单次渲染端到端总预算，默认 `120` 秒。
- `RENDER_MAX_ATTEMPTS`：单请求最大尝试次数，默认 `3`。
- `RENDER_SCHEDULER_POLL_INTERVAL_SECONDS`：渲染调度轮询间隔，默认 `0.25` 秒。
- `RENDER_ATTEMPT_LEASE_SECONDS`：单个 attempt 租约时长，默认 `60` 秒。
- `RENDER_UNKNOWN_RECONCILE_AFTER_SECONDS`：未知状态 attempt 等待对账窗口，默认 `15` 秒。
- `RENDER_ARTIFACT_MAX_BYTES`：单次渲染产物字节上限，默认 `33554432`（32 MiB）。
- `RENDER_RUNTIME_NAVIGATION_BASE_URL` / `RENDER_RUNTIME_ASSET_BASE_URL` / `RENDER_PLATFORM_ASSET_BASE_URL`：渲染器回源基址，默认自动根据平台与 Runtime 地址推导。

### 5. 项目构建持久领取

- `PROJECT_BUILD_LEASE_SECONDS`：构建任务持久领取租约，默认 `960` 秒。
- `PROJECT_BUILD_MAX_ATTEMPTS`：构建任务最大重试次数，默认 `3`。
- `PROJECT_BUILD_TOTAL_DEADLINE_SECONDS`：构建任务绝对硬期限，默认 `3600` 秒。
- `PROJECT_BUILD_QUEUE_POLL_INTERVAL_SECONDS`：构建队列轮询周期，默认 `1.0` 秒。
- `PROJECT_BUILD_ARTIFACT_MAX_BYTES`：构建结果归档包接收上限，默认 `536870912` 字节（512 MiB）。

### 6. Runtime 角色扩容与 Worker 内存管理

- `RUNTIME_TARGET_FAILURE_THRESHOLD`：目标连续失败熔断阈值，默认 `3`。
- `RUNTIME_TARGET_COOLDOWN_SECONDS`：熔断后冷却时长，默认 `15` 秒。
- `RUNTIME_CHECK_MAX_INFLIGHT` / `RUNTIME_LIGHT_MAX_INFLIGHT`：Backend 内部调用并发准入上限，默认 `16`。
- `RUNTIME_VITE_TASK_CONCURRENCY`：Runtime Vite 任务并发，默认 `2`。
- `RUNTIME_VITE_TASK_QUEUE_SIZE`：Runtime Vite 任务队列深度，默认 `16`。
- `RUNTIME_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS`：排队等待超时，默认 `30000` 毫秒。
- `RUNTIME_VITE_DIAGNOSTICS_WEIGHT`：诊断任务在多任务执行时的权重，默认 `3`。
- `RUNTIME_LIGHT_TOOL_CONCURRENCY` / `RUNTIME_LIGHT_TOOL_QUEUE_SIZE` / `RUNTIME_LIGHT_TOOL_QUEUE_WAIT_TIMEOUT_MS` / `RUNTIME_LIGHT_TOOL_TIMEOUT_MS`：轻量级内部工具独立容量与超时设置。
- `RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB`：构建 Worker Node.js 最大旧生代堆内存，默认 `2048` MiB。
- `RUNTIME_BUILD_WORKER_TIMEOUT_MS`：构建 Worker 执行超时，默认 `600000` 毫秒（10 分钟）。
- `RUNTIME_DIAGNOSTICS_WORKER_*`：编译诊断 Worker 复用、超时、最大任务数及 RSS 内存回收阈值（默认 `0.75`）。

### 7. 内存型运行态缓存预算

- `RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS`：`memory://` artifact 过期扫描周期，默认 `30` 秒。
- `RUNTIME_STATE_MEMORY_MAX_BYTES`：进程内 `memory://` 运行态总 payload 预算，默认 `134217728` 字节（128 MiB）。
- `RUNTIME_STATE_MEMORY_MAX_ITEM_BYTES`：进程内 `memory://` 单项 payload 上限，默认 `16777216` 字节（16 MiB）。
- `RUNTIME_RSA_ALLOW_AUTO_GENERATE`：单实例/Lite 缺省密钥时是否自动生成，默认 `true`。
