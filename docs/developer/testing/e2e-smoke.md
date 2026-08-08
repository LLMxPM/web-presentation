# 平台 E2E

平台 E2E 使用 Playwright 覆盖轻量主流程、可视化编辑、真实 Backend AI mock 链路和 Runtime 重型链路，测试文件位于 `tests/e2e/`。

## 运行命令

```powershell
pnpm run test:e2e
```

该命令会先重置测试数据、播种 smoke 数据并确认服务，再执行 `auth + smoke`。

扩展回归与全量：

```powershell
pnpm run test:e2e:regression
pnpm run test:e2e:all
```

`regression` 运行 `visual-edit + ai + runtime-heavy`；`all` 运行全部 project。

只执行 Playwright：

```powershell
pnpm run test:e2e:run
```

`test:e2e:run` 不修改数据库，只适合已执行过 prepare 的快速重跑。globalSetup 会校验 Backend 的 E2E 数据库、Redis、seed 版本和 smoke 数据；不匹配时快速失败并给出 prepare 提示。

## Project 分层

| Project | 范围 | storageState |
| :--- | :--- | :--- |
| `auth` | 未登录重定向与登录成功 | 空状态 |
| `smoke` | 登录后的只读核心链路和入口可见性 | 复用全局登录态 |
| `visual-edit` | 用例级独立项目/页面的真实写入 | 复用全局登录态 |
| `ai` | FunctionModel、图片理解、图片生成与 deferred 恢复 | 复用全局登录态 |
| `runtime-heavy` | 真实截图/构建与产物 | 复用全局登录态 |

`auth` 与 `smoke` 没有 project dependency，可以并行执行；登录态由 globalSetup 生成。

## 服务启动

E2E 入口默认由脚本自启服务：未显式设置 `TESTING_START_*` 时，`prepare` 会先校验 8000/5173/7373 端口与本地 PostgreSQL/Redis 依赖，端口被占用时立即报错并给出提示，校验通过后自动注入 `TESTING_START_*` 与 `AI_TEST_MODE=mock` 并启动服务。

复用已在运行的服务时，显式设置任一 `TESTING_START_*` 或 `TESTING_REUSE_BACKEND` 会跳过端口校验：

```powershell
$env:TESTING_REUSE_BACKEND='true'   # 复用 Backend（必须满足 E2E 测试指纹）
pnpm run test:e2e
```

## 报告目录

- `test-results/e2e/html-report/`：Playwright HTML 报告。
- `test-results/e2e/artifacts/`：trace、截图、视频和 `.last-run.json`。
- `test-results/e2e/services/`：测试脚本启动的 Backend、Editor、Runtime 日志。
- 失败用例会附加 API 4xx/5xx/requestfailed 摘要；AI run 失败时附加只读诊断 CLI 输出。

`test-results/e2e/storage-state.json` 含认证 cookie，只供本地测试进程读取，不得提交或上传为 CI artifact。

## AI smoke

E2E 使用 `AI_TEST_MODE=mock`，避免依赖真实 LLM 响应顺序、时延和内容。内容助手、图片理解和图片生成分别使用 `e2e-mock-agent-*`、`e2e-mock-vision-*`、`e2e-mock-image-*`；浏览器侧不得拦截 `/api/ai/**`。
