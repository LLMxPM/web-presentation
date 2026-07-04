# 部署环境变量

production env 版通过 `deploy/.env` 管理环境变量，模板来自 `deploy/.env.example`。两个简化版 compose 不读取该文件，而是在 compose 文件内直接写变量。

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
| `DATABASE_URL` | PostgreSQL 连接串 |
| `REDIS_URL` | Redis 连接串 |
| `REDIS_KEY_PREFIX` | Redis key 前缀，建议同一 Redis 多环境隔离 |

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

## 资源存储

| 变量 | 说明 |
| :--- | :--- |
| `ASSET_STORAGE_DRIVER` | `local` 或 `s3` |
| `S3_ENDPOINT_URL` | S3 兼容服务地址 |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | S3 访问凭证 |
| `S3_BUCKET` | 私有资源 bucket |
| `S3_PUBLIC_BUCKET` | 可选公开字体 bucket |
| `S3_PUBLIC_BASE_URL` | 公开资源访问地址 |
