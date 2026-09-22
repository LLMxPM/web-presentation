# 部署环境变量

production env 版通过 `deploy/.env` 管理环境变量，模板来自 `deploy/.env.example`。SQLite 轻量单容器版和两个简化版 compose 不读取该文件，而是在 compose 文件内直接写变量。

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
| `REDIS_URL` | 运行态存储连接串；常规部署使用 Redis，SQLite 轻量模式使用 `memory://lite` |
| `REDIS_KEY_PREFIX` | Redis 或 memory runtime key 前缀，建议同一运行态多环境隔离 |

SQLite 轻量模式不依赖外部 PostgreSQL/Redis。`memory://` 运行态只保存在当前 Backend 进程内，容器重启后短生命周期预览 artifact、锁和构建运行态会失效；主数据仍保存在 SQLite 文件中。

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
| `RUNTIME_BACKEND_API_BASE_URL` | Runtime 回源 Backend 的内网地址 |
| `RUNTIME_PREVIEW_JWKS_URL` | Runtime 校验预览令牌的 JWKS 地址 |
| `RUNTIME_SERVER_BASE_PATH` | Runtime Vite 资源挂载路径，同域部署通常为 `/runtime/` |
| `RUNTIME_*_TOKEN_AUDIENCE` | 预览、构建和诊断令牌 audience |

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
