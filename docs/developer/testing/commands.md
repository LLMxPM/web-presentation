# 测试命令

根仓通过 `package.json` 统一暴露常用测试入口。

## Backend

```powershell
pnpm run test:backend
pnpm run test:backend:unit
pnpm run test:backend:api
pnpm run test:backend:integration
```

Backend 底层使用 `uv run --project backend pytest -c backend/pyproject.toml`。

## Editor

```powershell
pnpm run test:editor
pnpm run test:editor:check
pnpm run test:editor:gate
```

`test:editor` 只执行 Vitest；需要类型检查和测试门禁时使用 `test:editor:gate`。

## Runtime

```powershell
pnpm run test:runtime
pnpm run test:runtime:delegated
pnpm run test:runtime:gate
```

`test:runtime` 和 `test:runtime:delegated` 只委托 Runtime Vitest；完整门禁使用 `test:runtime:gate`。

## 契约与 E2E

```powershell
pnpm run test:contracts
pnpm run test:e2e:run
pnpm run test:e2e
pnpm run test:e2e:regression
pnpm run test:e2e:all
```

- `test:e2e:run`：只运行 `auth + smoke`，不准备环境；globalSetup 会校验 smoke 数据指纹，未准备时提示先执行 prepare。
- `test:e2e:prepare`：准备 E2E 环境，等价于 `node scripts/testing/prepare-e2e-env.mjs`。未显式设置 `TESTING_START_*` / `TESTING_REUSE_BACKEND` 时进入自启模式：先校验 8000/5173/7373 端口与本地 PostgreSQL/Redis 依赖，端口被占用或依赖缺失时立即报错并给出提示；校验通过后自动注入 `TESTING_START_*` 与 `AI_TEST_MODE=mock`，随后重置数据、播种 smoke 数据并启动/确认服务。
- `test:e2e`：准备环境后运行 `auth + smoke`。
- `test:e2e:regression`：准备环境后运行 `visual-edit + ai + runtime-heavy`。
- `test:e2e:all`：准备环境后运行全部 Playwright project。

复用已有服务时，显式设置 `TESTING_START_*` 或 `TESTING_REUSE_BACKEND` 会跳过端口校验；复用 Backend 必须满足 E2E 测试指纹。

单独准备数据与服务：

```powershell
pnpm run test:e2e:prepare
```

## 全量

```powershell
pnpm run test:all
```

`test:all` 是本地全量入口，依次执行 Backend pytest（全部 marker）、Editor gate、Runtime gate、根仓 contracts 和全部 E2E project（auth + smoke + visual-edit + ai + runtime-heavy）。

脚本会自动完成环境准备，无需手动设置环境变量：

- 先校验 Backend/Editor/Runtime 端口（默认 8000/5173/7373）未被占用，并检查本地 PostgreSQL/Redis 依赖（`docker compose -f docker-compose.dev.yml up -d --wait`）；
- 校验失败立即报错并提示处理方式，不会进入任何测试阶段；
- 校验通过后自动注入 `TESTING_START_BACKEND/EDITOR/RUNTIME=true` 与 `AI_TEST_MODE=mock` 并自启服务；
- 任一阶段失败即中止后续阶段。

若确实想复用已在运行的 Backend，可设置 `TESTING_REUSE_BACKEND=true` 跳过其端口校验，但该服务必须满足 E2E 测试指纹。

全量测试耗时较长（含真实构建与完整 E2E），通常用于大范围改动或发布前验证。
