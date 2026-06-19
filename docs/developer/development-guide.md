<!-- 文件功能：说明 web-presentation 本地开发依赖、测试入口、测试数据准备和 Redis 运行态维护方式。 -->
# 开发与测试指南

## 环境要求

- 前端包管理使用 `pnpm`。
- Backend 使用 `uv` 管理 Python 依赖。
- 本地 PostgreSQL 与 Redis 通过根目录 `docker-compose.dev.yml` 启动。
- `runtime/` 是独立子项目，进入子目录后按它自己的 `package.json` 执行命令。

## 本地启动总览

本地完整联调通常需要四类进程：

1. `docker-compose.dev.yml`：只启动 PostgreSQL 与 Redis。
2. Backend：监听 `127.0.0.1:8000`，负责 API、登录、AI Agent、预览 artifact、截图和构建任务。
3. Runtime：监听 `127.0.0.1:7373`，负责预览、代码检查、截图和构建。
4. Editor：监听 Vite 默认端口，负责创作工作台页面。

如果这些服务已经在本机运行，先用 `docker compose -f .\docker-compose.dev.yml ps` 或查看现有终端确认状态，不要重复启动。

## 本地基础服务

在仓库根目录启动 PostgreSQL 与 Redis：

```powershell
docker compose -f .\docker-compose.dev.yml up -d
```

`docker-compose.dev.yml` 保留在仓库根目录，因为它是本地开发和 CI 测试共享的基础设施入口，不属于 `deploy/` 下的交付部署模板。当前 `.github/workflows/*`、本指南、测试治理文档和 Backend README 都直接引用该路径；如果未来移动文件，需要同步更新这些引用。

Backend 测试默认会把 `REDIS_URL` 设置为 `memory://test`，不依赖本机 Redis。手动联调预览、截图、代码检查、构建等临时 artifact 能力时必须启动 Redis；AI run/HITL 状态由 Backend 主库中的平台运行态表承担，不再依赖 Redis。

## Backend 本地启动

首次启动前在新的终端中，从仓库根目录进入 `backend/` 并准备环境变量和依赖：

```powershell
cd .\backend
Copy-Item .\.env.example .\.env
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed_admin
```

启动 Backend 开发服务：

```powershell
uv run uvicorn app.main:app --reload
```

默认管理员账号来自 `backend/.env`：`admin` / `Admin123456`。如果需要调整默认账号，修改 `DEFAULT_ADMIN_USERNAME`、`DEFAULT_ADMIN_PASSWORD` 和 `DEFAULT_ADMIN_DISPLAY_NAME` 后重新启动 Backend。

## Runtime 本地启动

Runtime 是独立子项目。首次启动前在新的终端中，从仓库根目录进入 `runtime/` 并准备环境变量和依赖：

```powershell
cd .\runtime
Copy-Item .\.env.example .\.env
pnpm install
```

启动 Runtime 开发服务：

```powershell
pnpm dev
```

默认配置会让 Runtime 通过 `http://127.0.0.1:8000` 回源 Backend，并监听 `127.0.0.1:7373`。如果 Backend 或 Runtime 端口变化，需要同步调整 `backend/.env` 中的 `RUNTIME_BASE_URL`、`RUNTIME_PUBLIC_BASE_URL`，以及 `runtime/.env` 中的 `RUNTIME_BACKEND_API_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL`。

## Editor 本地启动

首次启动前在新的终端中，从仓库根目录进入 `editor/` 并准备环境变量和依赖：

```powershell
cd .\editor
Copy-Item .\.env.example .\.env
pnpm install
```

启动 Editor 开发服务：

```powershell
pnpm dev
```

Editor 默认通过 Vite 代理把同源 `/api` 转发到 `http://127.0.0.1:8000`。本地登录时优先使用 Editor 页面入口，不要混用 `localhost` 和 `127.0.0.1`，避免 Cookie 站点不一致导致后续接口返回 `401`。

## 根仓测试入口

```powershell
pnpm install
pnpm run test:backend
pnpm run test:editor
pnpm run test:runtime:delegated
pnpm run test:contracts
pnpm run test:e2e
```

常用分层：

- `pnpm run test:backend`：Backend pytest。
- `pnpm run test:editor`：Editor Vitest。
- `pnpm run test:contracts`：根仓跨模块契约测试。
- `pnpm run test:e2e`：平台 Playwright smoke。
- `pnpm run test:runtime:delegated`：委托执行 Runtime 子项目测试。

详细测试治理见 [测试治理说明](./testing-strategy.md)。

## 测试数据

平台 smoke 数据 CLI：

```powershell
pnpm run test:reset:data
pnpm run test:seed:smoke
```

E2E 默认应使用 `AI_TEST_MODE=mock`，避免依赖真实 LLM 响应顺序、时延和内容。

## Redis 临时态维护

Redis 保存预览 artifact、截图锁与构建心跳等临时运行态，不保存 AI run/HITL 事实源。

AI run 状态已经切到平台自有 `ai_agent_*` 表；旧 Redis run key 不需要维护脚本清理，按已有 TTL 自然过期。

## Runtime 子项目命令

```powershell
pnpm --dir runtime install
pnpm --dir runtime check
pnpm --dir runtime test
pnpm --dir runtime build
```

Runtime 内部能力、运行方式和镜像发布见 [runtime/README.md](../../runtime/README.md)。
