# 环境变量管理与索引

平台采用**“根仓单一事实源 + 级联智能继承 + 跨模块一致性校验”**的环境变量管理体系。

本地开发推荐直接在仓库根目录维护一份统一的 `.env`，所有子模块（Backend、Editor、Runtime、Renderer）均默认向上查找根目录配置并自动对齐；同时保留子模块目录的 `.env` 局部覆盖能力。

生产部署变量详见 [部署环境变量](../deployment/env-vars.md)。

---

## 本地开发统一管理

- **统一模板文件**：根目录 `.env.example`。
- **快速初始化**：
  ```bash
  cp .env.example .env
  pnpm run env:check
  ```
- **加载与覆盖优先级**：
  1. 系统 / 容器宿主环境变量（最高优先级）
  2. 当前工作目录（CWD）`.env`
  3. 子模块目录（如 `backend/.env`、`renderer/.env`）
  4. 仓库根目录 `.env`（开发期单一事实源）

通过 `pnpm run env:check` 脚本可随时执行全仓配置体检，自动核对 Backend、Runtime、Renderer、Editor 的端口、URL、Audience 与认证凭据一致性。

---

## 各模块变量索引与说明

### 1. 跨模块共享与基础配置 (SHARED)
- `APP_TIMEZONE`：平台业务时区，统一以 Backend 为准，Editor 启动时自动读取。
- `BACKEND_PUBLIC_BASE_URL`：平台对外服务基址，默认 `http://127.0.0.1:8000`。
- `RUNTIME_PUBLIC_BASE_URL`：Runtime 对外访问基址，默认 `http://127.0.0.1:7373`。
- `RENDER_SERVICE_CREDENTIAL`：Backend 与 Renderer 之间的共享安全凭证，本地开发统一在根目录配置一次，两侧自动对齐。
- `RUNTIME_*_TOKEN_AUDIENCE`：Backend 与 Runtime 之间的令牌受众声明集合。

### 2. Backend 后台变量
- 对应模块：`backend/`（模板：`backend/.env.example` 或根目录 `.env.example`）。
- 关键变量：`DATABASE_URL`、`REDIS_URL`、`DEFAULT_ADMIN_*`、`SESSION_*`、`RUNTIME_BASE_URL`、`AI_*`、`PAGE_SCREENSHOT_*` 与 `ASSET_STORAGE_DRIVER`。

### 3. Editor 编辑器变量
- 对应模块：`editor/`（模板：`editor/.env.example` 或根目录 `.env.example`）。
- 关键变量：`VITE_API_PROXY_TARGET`（API 代理目标）、`VITE_CLIENT_ERROR_REPORTING`。

### 4. Runtime 运行时变量
- 对应模块：`runtime/`（模板：`runtime/.env.example` 或根目录 `.env.example`）。
- 关键变量：`RUNTIME_PREVIEW_JWKS_URL`、`RUNTIME_BACKEND_API_BASE_URL`、`RUNTIME_SERVER_HOST`、`RUNTIME_SERVER_PORT`、`RUNTIME_SERVER_BASE_PATH` 与 Vite Worker 资源限制参数。

### 5. Renderer 渲染执行服务变量
- 对应模块：`renderer/`（模板：`renderer/.env.example` 或根目录 `.env.example`）。
- 关键变量：`RENDER_WORKER_ID`、`RENDER_PORT`、`RENDER_SERVICE_CREDENTIAL`（严禁弱占位符，fail-closed）、`RENDER_PROFILE_DIGEST`。

---

## 生产变量

- 模板文件：`deploy/.env.example`。
- 由 `deploy/docker-compose.production.yml` 通过 `env_file: .env` 读取，两个简化版 compose 文件不读取该文件。
- 生产环境必须长期保存 `AI_SECRET_ENCRYPTION_KEY`，并使用独立的 `deploy/secrets/render_service_credential` 密钥文件。
