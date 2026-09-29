# 测试命令

根仓通过 `package.json` 统一暴露常用测试入口。

根仓 Vitest 配置位于 `tests/config/vitest.config.ts`，Playwright 配置位于 `tests/config/playwright.config.ts`。根仓相关 `pnpm run` 脚本已显式指定配置；手动直接调用 `vitest` 或 `playwright test` 时也应传入对应 `--config`。

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
pnpm run test:editor:build
pnpm run test:editor:gate
```

`test:editor` 只执行 Vitest；`test:editor:check` 执行类型检查；`test:editor:build` 执行生产构建；完整门禁使用 `test:editor:gate`。

## Runtime

```powershell
pnpm run test:runtime
pnpm run test:runtime:gate
```

`test:runtime` 只执行 Runtime Vitest；完整门禁使用 `test:runtime:gate`。

## 契约与 E2E

```powershell
pnpm run test:contracts
pnpm run test:contracts:generated
pnpm run test:repository
pnpm run test:python-workspace
pnpm run test:contracts:docker-context
pnpm run test:render-contracts
pnpm run test:renderer
pnpm run test:render-e2e
pnpm run test:contracts:gateway
pnpm run test:contracts:cli-skill
pnpm run test:e2e:run
pnpm run test:e2e
pnpm run test:e2e:regression
pnpm run test:e2e:all
```

- `test:contracts:generated`：在隔离配置下从当前 Backend 重导 OpenAPI，核对 API 与两端 previewSchema 生成物；不启动业务服务。契约修改后先运行 `codegen:editor-api` / `codegen:preview-types`。
- `test:e2e:run`：只运行 `auth + smoke`，不准备环境；globalSetup 会校验 smoke 数据指纹，未准备时提示先执行 prepare。
- `test:e2e:prepare`：准备 E2E 环境，等价于 `node scripts/testing/prepare-e2e-env.mjs`。未显式设置 `TESTING_START_*` / `TESTING_REUSE_BACKEND` 时进入自启模式：先校验 8000/5173/7373/7400 端口与本地 PostgreSQL/Redis 依赖，端口被占用或依赖缺失时立即报错并给出提示；校验通过后自动注入 `TESTING_START_*` 与 `AI_TEST_MODE=mock`，随后重置数据、播种 smoke 数据并启动/确认服务。
- `test:e2e`：准备环境后运行 `auth + smoke`。
- `test:e2e:regression`：准备环境后运行 `visual-edit + ai + runtime-heavy`。
- `test:e2e:all`：准备环境后运行全部 Playwright project，默认使用 2 workers，与 GitHub Actions release/test workflow 一致；本地并行调试可通过 `PLAYWRIGHT_WORKERS` 覆盖。

GitHub Actions 的 release/test workflow 共用 `.github/actions/setup-e2e`，使用锁文件安装依赖、固定 uv/pnpm 版本，并缓存 Playwright 浏览器；本地测试仍按上面的命令执行即可。

复用已有服务时，显式设置 `TESTING_START_*` 或 `TESTING_REUSE_BACKEND` 会跳过端口校验；复用 Backend 必须满足 E2E 测试指纹。

单独准备数据与服务：

```powershell
pnpm run test:e2e:prepare
```

## 全量

```powershell
pnpm run test:all
```

`test:all` 是本地全量入口，依次执行 Backend pytest（全部 marker）、Editor gate、Runtime gate、根仓 contracts、渲染契约、Renderer、Python workspace 共装验证和全部 E2E project（auth + smoke + visual-edit + ai + runtime-heavy）。

脚本会自动完成环境准备，无需手动设置环境变量：

- 先校验 Backend/Editor/Runtime/Renderer 端口（默认 8000/5173/7373/7400）未被占用，并检查本地 PostgreSQL/Redis 依赖（`docker compose -f scripts/dev/compose.infra.yml up -d --wait`）；
- 校验失败立即报错并提示处理方式，不会进入任何测试阶段；
- 校验通过后自动注入 `TESTING_START_BACKEND/EDITOR/RUNTIME/RENDERER=true` 与 `AI_TEST_MODE=mock` 并自启服务；
- 任一阶段失败即中止后续阶段。

若确实想复用已在运行的 Backend，可设置 `TESTING_REUSE_BACKEND=true` 跳过其端口校验，但该服务必须满足 E2E 测试指纹。

全量测试耗时较长（含真实构建与完整 E2E），通常用于大范围改动或发布前验证。

## 仓库边界与真实渲染验证

- `test:repository`：根契约测试的子集，校验文档本地链接、代码围栏、交付 Dockerfile 覆盖、Compose 文件位置、共享 workspace 的 CI 触发范围与环境覆盖逻辑。
- `test:python-workspace`：在全部 Python 成员共装后，从根目录、Backend、Renderer 分别导入 `app`、`wp_renderer`、`render_contracts`，并验证根目录诊断 CLI。
- `test:contracts:docker-context`：向 Docker 发送临时合成配置，验证所有模块的 `.env`、密钥与缓存不会进入构建上下文，示例文件仍可交付。
- `test:render-contracts` / `test:renderer`：纯契约与 Renderer 单元测试。
- `test:render-e2e`：准备 E2E 环境后运行真实页面截图 smoke，覆盖四服务链路并检查 PNG 文件头、尺寸与任务状态，不再使用 Renderer 目录的占位用例。

运行 E2E 前分别执行 `pnpm exec playwright install chromium` 与 `uv run --project renderer playwright install chromium`；Linux 首次安装加 `--with-deps`。准备脚本会启动/确认 Renderer，并使用 Backend 真实客户端校验服务认证、Worker ID 和 profile。测试凭据使用专门的 `E2E_RENDER_SERVICE_CREDENTIAL`，可通过 `E2E_RENDERER_BASE_URL` 覆盖 Renderer 地址，禁止复用生产身份。

## 交付镜像与完整拓扑探针

以下命令只在已准备好的专用测试机器执行。`check-image-startup.py` 创建隔离临时容器；Renderer 通过真实控制 API 接管任务、调用生产执行器，下载 PNG 并检查双色 fixture、校验和与槽位释放。脚本不再手工调用 Playwright 或覆盖浏览器参数。其它镜像只报告入口与健康，不报告业务执行通过。

```powershell
python scripts/contracts/check-image-startup.py --image $env:WP_SMOKE_IMAGE --variant renderer --output-dir test-results/images/renderer-candidate
```

产物包括 `image.json`（实际容器镜像 ID、repo digests、OS/CPU 架构）、`receipt.json` 和 `page.png`；CI 镜像 action 自动归档。仅构建了 arm64 manifest 不能代替在 arm64 实际执行该命令。失败时保留未通过状态，不覆写已有证据目录。

完整拓扑复用已经启动的 Gateway、Backend、Runtime、Renderer，**不会启动服务或重置数据**。准备独立测试账号，设置 `WP_SMOKE_USERNAME` / `WP_SMOKE_PASSWORD`；另设置以下命令中的测试地址、页面和项目 ID。它会对指定实体创建截图与构建任务，不应指向生产数据。

```powershell
python scripts/contracts/check-deployment-pipeline.py --base-url $env:WP_SMOKE_BASE_URL --page-id $env:WP_SMOKE_PAGE_ID --project-id $env:WP_SMOKE_PROJECT_ID --output-dir test-results/deployment/candidate
```

该探针拒绝失败/取消/跳过任务，检查截图版本、PNG 解码和视口、ZIP SHA-256/大小及 HTML 入口，输出 `pipeline.json`、`page.png`、`build.zip`。失败摘要保存已创建的任务 ID；超时不会自动取消仍在运行的任务。Cookie 只保留于内存，报告不保存密码、下载令牌或业务响应全文。

此入口补足 M01 的截图与产物下载准备，不替代浏览器打开最终构建站点、Compose 全模板版本清单、双架构执行、容量或故障恢复验收。图片与 ZIP 仍须随候选 SHA、各服务实际镜像身份和环境配置一起归档。当前新增探针仅通过本地模拟传输与产物反例测试，真实容器和拓扑执行留待下一轮。
