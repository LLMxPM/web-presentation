# 环境变量索引

环境变量分为本地开发和生产部署两类。生产部署变量详见 [部署环境变量](../deployment/env-vars.md)。

## Backend 本地变量

模板文件：`backend/.env.example`。

关键变量包括 `DATABASE_URL`、`REDIS_URL`、`DEFAULT_ADMIN_*`、`SESSION_*`、`RUNTIME_BASE_URL`、`RUNTIME_PUBLIC_BASE_URL`、`BACKEND_PUBLIC_BASE_URL`、`AI_*`、`PAGE_SCREENSHOT_*` 和 `ASSET_STORAGE_DRIVER`。

## Editor 本地变量

模板文件：`editor/.env.example`。

关键变量包括 `VITE_API_PROXY_TARGET`、`VITE_APP_TIMEZONE` 和 `VITE_CLIENT_ERROR_REPORTING`。

## Runtime 本地变量

模板文件：`runtime/.env.example`。

关键变量包括 `RUNTIME_PREVIEW_JWKS_URL`、`RUNTIME_BACKEND_API_BASE_URL`、`RUNTIME_SERVER_HOST`、`RUNTIME_SERVER_PORT`、`RUNTIME_SERVER_BASE_PATH`、`RUNTIME_*_TOKEN_AUDIENCE` 和 `RUNTIME_STANDALONE_PREVIEW_ENABLED`。

## 生产变量

模板文件：`deploy/.env.example`。production env 版 compose 读取该文件，两个简化版 compose 不读取。

生产环境必须长期保存 `AI_SECRET_ENCRYPTION_KEY`，并确保 Backend 与 Runtime 的内网地址、公网地址和 base path 一致。
