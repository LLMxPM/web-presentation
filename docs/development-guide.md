<!-- 文件功能：说明 web-presentation 本地开发依赖、测试入口、测试数据准备和 Redis 运行态维护方式。 -->
# 开发与测试指南

## 环境要求

- 前端包管理使用 `pnpm`。
- Backend 使用 `uv` 管理 Python 依赖。
- 本地 PostgreSQL 与 Redis 通过根目录 `docker-compose.dev.yml` 启动。
- `runtime/` 是独立子项目，进入子目录后按它自己的 `package.json` 执行命令。

## 本地基础服务

在仓库根目录启动 PostgreSQL 与 Redis：

```powershell
docker compose -f .\docker-compose.dev.yml up -d
```

Backend 测试默认会把 `REDIS_URL` 设置为 `memory://test`，不依赖本机 Redis。手动联调预览、截图、代码检查、AI 后台 run 或构建时必须启动 Redis。

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

## Redis 运行态维护

Redis 保存 Agent run、SSE 事件、预览 artifact、截图锁与构建心跳等正在发生的运行态，不保存长期业务事实。

Redis 运行态切换维护窗口前，可在 `backend/` 下执行旧 active run 检查：

```powershell
uv run python -m app.scripts.prepare_redis_runtime_cutover
uv run python -m app.scripts.prepare_redis_runtime_cutover --migrate-paused
uv run python -m app.scripts.prepare_redis_runtime_cutover --force-cancel-active --migrate-paused
```

默认发现 `pending`、`running` 或 `cancelling` 会阻断；确认切换时再显式迁移 paused 或强制取消 active。

## Runtime 子项目命令

```powershell
pnpm --dir runtime install
pnpm --dir runtime check
pnpm --dir runtime test
pnpm --dir runtime build
```

Runtime 内部能力、运行方式和镜像发布见 [runtime/README.md](../runtime/README.md)。
