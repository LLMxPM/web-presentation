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

## 预览正常但截图失败

先检查 `renderer` 容器健康与日志，再核对 Backend 的 `RENDER_WORKERS_CONFIG`、Renderer 的 `RENDER_WORKER_ID`、两侧共享凭据及 `RENDER_PROFILE_DIGEST`。Renderer 还必须能访问 Runtime 的预览文档和静态资源；Backend 不在本进程内执行 Chromium。

## AI 设置保存后无法解密或启动报密钥占位错误

若后端启动报 `SigningIdentityError: AI_SECRET_ENCRYPTION_KEY 禁止使用默认/示例占位值`，说明配置了内置示例弱密钥被安全拦截；若启动后进入 AI 页面解密失败（报 `500 AI_LLM_API_KEY_INVALID`），通常是 `AI_SECRET_ENCRYPTION_KEY` 改变导致。
- 若需要更换密钥并保留现有凭证，必须按照 [AI 凭证密钥轮换与迁移指南](../backend/ai-secret-rotation.md) 运行平滑重密迁移脚本。
- 若原密钥完全丢失，已有用户模型凭证无法自动解密恢复，可按指南执行 `reset_ai_model_configuration` 清空配置后重新录入。

## 图片、字体或构建产物无法访问

local 模式检查 Backend 数据 volume；S3 模式检查 bucket、凭证、region 和 `S3_PUBLIC_BASE_URL`。字体公开 bucket 配置错误会导致页面预览可运行但字体不生效。
