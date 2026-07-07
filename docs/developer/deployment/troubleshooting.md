# 部署排障

## 入口健康但接口失败

检查 Gateway 是否正确代理 `/api` 到 Backend，Backend 是否已完成数据库迁移，浏览器访问地址是否在 `CORS_ORIGINS` 中。

## 数据库迁移失败

先查看 `backend-migrate` 或 `platform` 容器日志，再确认数据库当前 `alembic_version` 和平台镜像内 migration 文件是否匹配。

## Runtime 预览不可用

检查：

- `RUNTIME_BASE_URL` 是否是 Backend 可访问的 Runtime 内网地址。
- `RUNTIME_PUBLIC_BASE_URL` 是否是浏览器可访问地址。
- `RUNTIME_SERVER_BASE_PATH` 是否与公网 path 一致。
- Gateway 是否保留 `/runtime/` 前缀代理到 Runtime。
- `RUNTIME_PREVIEW_JWKS_URL` 和 audience 是否一致。

## AI 设置保存后无法解密

通常是 `AI_SECRET_ENCRYPTION_KEY` 改变导致。恢复原密钥后重启 Backend；如果原密钥丢失，已有用户模型凭证无法自动恢复，需要用户重新配置。

## 图片、字体或构建产物无法访问

local 模式检查 Backend 数据 volume；S3 模式检查 bucket、凭证、region 和 `S3_PUBLIC_BASE_URL`。字体公开 bucket 配置错误会导致页面预览可运行但字体不生效。
