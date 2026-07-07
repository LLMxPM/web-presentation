# E2E smoke

E2E smoke 使用 Playwright 覆盖平台主流程，测试文件位于 `tests/e2e/`。

## 运行命令

```powershell
pnpm run test:e2e
```

该命令会先重置测试数据、播种 smoke 数据并确认服务，再执行 Playwright。

只执行 Playwright：

```powershell
pnpm run test:e2e:run
```

## 服务启动

E2E 默认不会主动启动 Backend、Editor、Runtime。如果需要由测试脚本启动服务，在当前命令环境中设置：

```powershell
$env:TESTING_START_BACKEND='true'
$env:TESTING_START_EDITOR='true'
$env:TESTING_START_RUNTIME='true'
pnpm run test:e2e
```

## 报告目录

- `test-results/e2e/html-report/`：Playwright HTML 报告。
- `test-results/e2e/artifacts/`：trace、截图、视频和 `.last-run.json`。

## AI smoke

E2E 默认应使用 `AI_TEST_MODE=mock`，避免依赖真实 LLM 响应顺序、时延和内容。
