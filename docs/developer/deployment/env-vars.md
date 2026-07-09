# 部署环境变量

production env 版通过 `deploy/.env` 管理环境变量，模板来自 `deploy/.env.example`。SQLite 轻量单容器版和两个简化版 compose 不读取该文件，而是在 compose 文件内直接写变量。

## 对外访问

| 变量 | 说明 |
| :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | 平台对外访问地址 |
| `RUNTIME_PUBLIC_BASE_URL` | Runtime 对浏览器暴露的访问地址，同域部署通常为平台地址追加 `/runtime` |
| `CORS_ORIGINS` | 允许访问 Backend 的前端源 |
| `SESSION_SECURE` | HTTPS 部署应设为 `true` |
| `APP_TIMEZONE` | 业务时区，默认 `Asia/Shanghai` |

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

`AI_SECRET_ENCRYPTION_KEY` 必须是 32 字节随机值的 URL-safe base64 编码，通常长度为 44 个字符并以 `=` 结尾。更换该值会导致已有用户模型凭证无法解密。

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
