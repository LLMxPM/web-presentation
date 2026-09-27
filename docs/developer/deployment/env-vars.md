# 部署环境变量

production env 版通过 `deploy/.env` 管理环境变量，模板来自 `deploy/.env.example`。分角色单机版的 Backend 也读取该文件，Runtime 三角色只读取由 `deploy/runtime.env.example` 复制的 `deploy/runtime.env`；两份文件中的公开地址、令牌 audience 和路径须保持一致，平台密钥只放在 Backend 的 `deploy/.env`。SQLite 轻量单容器版和两个简化版 compose 不读取这些文件，而是在 compose 文件内直接写变量。

## 对外访问

| 变量 | 说明 |
| :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | 平台对外访问地址 |
| `RUNTIME_PUBLIC_BASE_URL` | Runtime 对浏览器暴露的访问地址，同域部署通常为平台地址追加 `/runtime` |
| `CORS_ORIGINS` | 允许访问 Backend 的前端源 |
| `SESSION_SECURE` | HTTPS 部署应设为 `true` |
| `APP_TIMEZONE` | 业务时区，默认 `Asia/Shanghai`；Editor 启动时自动读取，无需重建前端 |

数据库与接口统一使用 UTC，历史无时区值直接补 UTC。业务时区只影响展示和业务日期生成，详见[时间存储与展示](../backend/time-handling.md)。

## 数据与缓存

| 变量 | 说明 |
| :--- | :--- |
| `DATABASE_URL` | 主数据库连接串；常规部署使用 PostgreSQL，SQLite 轻量模式使用 `sqlite+aiosqlite:////app/backend/data/web_presentation.db` |
| `REDIS_URL` | 运行态存储连接串。常规部署使用 `redis://…`；SQLite 轻量模式**正式**使用 `memory://lite`（进程内适配器） |
| `REDIS_KEY_PREFIX` | Redis 或 `memory://` runtime key 前缀，建议同一运行态多环境隔离 |
| `TIKTOKEN_CACHE_DIR` | tiktoken 词表缓存目录。交付镜像已固定为 `/app/.cache/tiktoken` 并在构建期预置 `cl100k_base`，离线/气隙启动无需出网；覆盖该变量需自行保证缓存文件已存在 |

SQLite 轻量模式不依赖外部 PostgreSQL/Redis。`memory://` 是**受支持的运行态适配器**，与真实 Redis 同契约、不同边界：只保存在当前 Backend 进程内，容器重启后短生命周期预览 artifact、锁和构建运行态会失效；主数据仍保存在 SQLite 文件中。能力矩阵、重启语义与非目标见 [运行态存储适配器](../backend/runtime-state-adapter.md)。

## 默认管理员

| 变量 | 说明 |
| :--- | :--- |
| `DEFAULT_ADMIN_USERNAME` | 首次启动时使用的默认管理员账号 |
| `DEFAULT_ADMIN_PASSWORD` | 默认管理员密码，生产环境必须替换 |
| `DEFAULT_ADMIN_DISPLAY_NAME` | 默认管理员展示名 |

## AI 配置

| 变量 | 说明 |
| :--- | :--- |
| `AI_ENABLED` | 是否启用 AI 能力 |
| `AI_SECRET_ENCRYPTION_KEY` | 加密用户模型凭证的 Fernet 密钥，必须长期保存 |
| `AI_AGENT_STREAM_IDLE_TIMEOUT_SECONDS` | 模型请求流连续无事件时的失败阈值，默认 `180` 秒 |
| `AI_AGENT_TOOL_STREAM_IDLE_TIMEOUT_SECONDS` | 工具执行流连续无事件时的失败阈值，默认 `600` 秒；成员委派等长工具使用该阈值 |

`AI_SECRET_ENCRYPTION_KEY` 必须是 32 字节随机值的 URL-safe base64 编码，通常长度为 44 个字符并以 `=` 结尾。更换该值会导致已有用户模型凭证无法解密。

## 重资源队列

| 变量 | 说明 |
| :--- | :--- |
| `AI_PAGE_MUTATION_CONCURRENCY` | AI 页面创建/修改的持久化 Worker 数；SQLite lite 为 `1`，常规部署为 `2` |
| `AI_PAGE_MUTATION_MAX_ACTIVE_JOBS` | 全局活跃或等待页面变更任务上限；lite 为 `16`，常规部署为 `64` |
| `DURABLE_JOB_LEASE_SECONDS` / `DURABLE_JOB_HEARTBEAT_SECONDS` | 截图与 AI 页面任务的跨进程租约和心跳周期 |
| `RENDER_WORKERS_CONFIG` | 受信 Renderer Worker 地址 JSON 数组；每个条目含 `worker_id` 与 `base_url` |
| `RENDER_SERVICE_CREDENTIAL_FILE` | Backend/Renderer 共享服务密钥文件路径；与 `RENDER_SERVICE_CREDENTIAL` 二选一，禁止占位符与空文件 |
| `RENDER_SERVICE_CREDENTIAL` | 共享服务密钥明文（不推荐生产使用；优先 secret 文件） |
| `RENDER_PROFILE_DIGEST` | 当前发布要求的渲染环境指纹；与 Renderer 实际 profile 不一致时拒绝执行 |
| `RENDER_PROFILE_MANIFEST` | 可选：环境清单文件路径，用于核对渲染环境身份 |
| `RENDER_GLOBAL_CONCURRENCY` | 全局活动/未确认释放渲染执行上限；lite 为 `1` |
| `RENDER_WORKSPACE_CONCURRENCY` | 单工作空间活动渲染执行上限，默认 `1` |
| `RENDER_QUEUE_SIZE` | 全局待处理渲染请求上限，默认 `64` |
| `RENDER_WORKSPACE_QUEUE_SIZE` | 单工作空间待处理上限，默认 `16` |
| `RENDER_REQUEST_TIMEOUT_SECONDS` | 渲染阶段总预算（秒），默认 `120` |
| `RENDER_MAX_ATTEMPTS` | 单请求执行尝试上限，默认 `3` |
| `RENDER_SCHEDULER_POLL_INTERVAL_SECONDS` | 协调器调度轮询间隔，默认 `0.25` |
| `RENDER_ATTEMPT_LEASE_SECONDS` | attempt 占用租约时长，超时由协调器收敛释放 |
| `RENDER_UNKNOWN_RECONCILE_AFTER_SECONDS` | 未知结果 attempt 进入可回收窗口的等待秒数 |
| `RENDER_ARTIFACT_MAX_BYTES` | 单产物字节上限，默认 32MiB |
| `RENDER_RUNTIME_NAVIGATION_BASE_URL` | 浏览器访问预览文档的基址 |
| `RENDER_RUNTIME_ASSET_BASE_URL` | 浏览器访问 Runtime 静态资源的基址 |
| `RENDER_PLATFORM_ASSET_BASE_URL` | 浏览器访问平台资源的基址 |
| `RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS` | `memory://` artifact 过期扫描周期，默认 `30` 秒 |
| `RUNTIME_STATE_MEMORY_MAX_BYTES` | 进程内 `memory://` 运行态总 payload 预算，默认 `134217728`（128 MiB），超限写入返回容量错误而不是拖垮容器 |
| `RUNTIME_STATE_MEMORY_MAX_ITEM_BYTES` | 进程内 `memory://` 单项 payload 上限，默认 `16777216`（16 MiB） |

Renderer 容器还应设置 `RENDER_WORKER_ID`、`RENDER_SERVICE_CREDENTIAL_FILE`、`RENDER_PROFILE_DIGEST`；可选 `RENDER_CLEANUP_GRACE_SECONDS`（默认 5）、`RENDER_RESULT_TTL_SECONDS`（默认 600）。

Runtime 容器还应设置 `RUNTIME_VITE_TASK_CONCURRENCY`、`RUNTIME_VITE_TASK_QUEUE_SIZE`、`RUNTIME_DIAGNOSTICS_WORKER_REUSE_ENABLED` 和 `RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB`。完整默认值见 `runtime/.env.example`。

部署 compose 使用 Docker secrets：启动前必须创建 `deploy/secrets/render_service_credential`（强随机共享密钥，Backend 与 Renderer 一致）。示例：

```powershell
mkdir deploy/secrets
openssl rand -base64 48 | Out-File -Encoding ascii deploy/secrets/render_service_credential
```

## Runtime 内网关系

| 变量 | 说明 |
| :--- | :--- |
| `RUNTIME_BASE_URL` | Backend 调用 Runtime 的内网地址 |
| `RUNTIME_PREVIEW/BUILD/CHECK_BASE_URL` | 分角色部署时按职责覆盖的内网目标；留空回退 `RUNTIME_BASE_URL` |
| `RUNTIME_BUILD_BASE_URLS` / `RUNTIME_CHECK_BASE_URLS` | 计算角色多副本目标列表（JSON 数组或逗号分隔）；留空回退对应单地址。Backend 轮询选址，满载自动换副本。构建默认已改为 Worker 拉取，该列表只对 `RUNTIME_BUILD_EXECUTION_MODE=legacy-http` 兼容路径生效 |
| `RUNTIME_TARGET_FAILURE_THRESHOLD` / `RUNTIME_TARGET_COOLDOWN_SECONDS` | 选址冷却：目标连续失败达到阈值后短暂跳过，冷却到期自动恢复 |
| `RUNTIME_BUILD_MAX_INFLIGHT` / `RUNTIME_CHECK_MAX_INFLIGHT` | 全链路准入：Backend 同时在途的 build/check 内部调用上限，超限返回 `RUNTIME_ADMISSION_FULL`；全部副本满载返回 `RUNTIME_CAPACITY_EXCEEDED`（503，可重试） |
| `RUNTIME_BACKEND_API_BASE_URL` | Runtime 回源 Backend 的内网地址 |
| `RUNTIME_BUILD_ID` | 部署构建标识，输出到 `/__runtime_healthz` 的 `build_id`；滚动发布时用于核对新旧副本版本指纹 |
| `RUNTIME_PREVIEW_JWKS_URL` | Runtime 校验预览令牌的 JWKS 地址 |
| `RUNTIME_SERVER_BASE_PATH` | Runtime Vite 资源挂载路径，同域部署通常为 `/runtime/` |
| `RUNTIME_*_TOKEN_AUDIENCE` | 预览、构建和诊断令牌 audience |
| `RUNTIME_ROLE` | Runtime 运行角色：`all`（单实例模板默认）或 `preview` / `build` / `check`；分角色模板 `compose.runtime-roles.yml` 按容器覆盖。角色语义由 Runtime 角色逻辑（规划 T1-1）消费 |
| `RUNTIME_BUILD_EXECUTION_MODE` | 构建执行模式：`pull`（默认）由 Build Worker 领取任务并关闭 HTTP 同步派发入口；`legacy-http` 显式回退到 Backend→Runtime 长同步 RPC |
| `RUNTIME_BUILD_WORKER_CREDENTIAL` / `RUNTIME_BUILD_WORKER_CREDENTIAL_FILE` | Backend 与 `runtime-build` 共用的领取凭证，两侧必须一致；secret 文件要求 `0400`/`0600`。未配置时 claim API fail-closed、Worker 不启动，构建任务停在 `pending` |

分角色单机模板还会按角色容器覆盖 `RUNTIME_VITE_TASK_CONCURRENCY`、`RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB` 等执行预算，并为每个容器设置 `deploy.resources.limits`；取值依据见 [Compose 部署说明](./compose.md)「分角色单机」。pull 模式下单个 `runtime-build` 实例的并发等于其 project lane 并发，再加副本只需增加 `runtime-build` 容器（各自独立领取，无需 Backend 选址）；Check 角色仍由 Backend 轮询扩容，用 `RUNTIME_CHECK_BASE_URLS` 注册全部副本地址并按「副本数 × 单副本执行预算」上调准入上限，详见 [Compose 部署说明](./compose.md)「计算副本扩容」。

## 签名身份与多 Backend

| 变量 | 说明 |
| :--- | :--- |
| `RUNTIME_RSA_PRIVATE_KEY` | RS256 签名私钥 PEM 文本；不推荐长期写在 env 文件 |
| `RUNTIME_RSA_PRIVATE_KEY_FILE` | RS256 签名私钥文件路径（共享路径 / secret 挂载）；多 Backend 推荐 |
| `RUNTIME_RSA_KEY_ID` | 当前签名 `kid`，默认 `default-key-1` |
| `RUNTIME_RSA_PREVIOUS_KEYS` | 轮换期旧钥 JSON 数组，每项 `{"kid", "private_key_file"}` 或 `{"kid", "private_key"}`；仅验签与 JWKS 公布 |
| `RUNTIME_RSA_ALLOW_AUTO_GENERATE` | 缺省密钥时是否自动生成本地私钥，默认 `true`（仅单实例/Lite） |
| `BACKEND_MULTI_INSTANCE` | 声明多 Backend 副本部署，默认 `false`；开启后启动期强制共享密钥与对象存储前提 |
| `OBJECT_STORAGE_SHARED_VOLUME` | local 对象目录为跨副本共享卷时置 `true` 显式确认；多 Backend 下默认要求 `s3` |

私钥读取顺序：`RUNTIME_RSA_PRIVATE_KEY` → `RUNTIME_RSA_PRIVATE_KEY_FILE` → 旧版 `data/runtime_rsa_key.pem` → 单实例自动生成。多 Backend 副本必须共享同一签名私钥与对象存储；密钥轮换时旧票据在自身 TTL 内仍有效，移出旧钥后立即失效。完整前提、轮换步骤与旧票据语义见 [多 Backend 与密钥一致性](./multi-backend.md)。

## 日志

| 变量 | 说明 |
| :--- | :--- |
| `LOG_LEVEL` / `LOG_FORMAT` | Backend 业务日志等级与格式 |
| `ACCESS_LOG_ENABLED` | Backend 访问日志开关，部署模板默认 `false` |
| `CLIENT_ERROR_LOG_ENABLED` | 浏览器错误上报日志开关，默认保留 |
| `RUNTIME_LOG_LEVEL` / `RUNTIME_LOG_FORMAT` | Runtime 业务日志等级与格式 |
| `RUNTIME_ACCESS_LOG_ENABLED` | Runtime 访问日志开关，部署模板默认 `false` |

Gateway Nginx 访问日志在平台镜像配置中默认关闭；错误日志仍输出到标准错误。

## 资源存储

| 变量 | 说明 |
| :--- | :--- |
| `ASSET_STORAGE_DRIVER` | `local` 或 `s3` |
| `S3_ENDPOINT_URL` | S3 兼容服务地址 |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | S3 访问凭证 |
| `S3_BUCKET` | 私有资源 bucket |
| `S3_PUBLIC_BUCKET` | 可选公开字体 bucket |
| `S3_PUBLIC_BASE_URL` | 公开资源访问地址 |
