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
```

`test:e2e` 会先重置并播种 smoke 数据、确认服务，再执行 Playwright。`test:e2e:run` 只执行 Playwright。

## 全量

```powershell
pnpm run test:all
```

全量测试耗时较长，通常用于大范围改动或发布前验证。
