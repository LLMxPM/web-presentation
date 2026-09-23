<!-- 文件功能：定义平台仓库测试分层、目录归属、命令入口、CI 策略与 E2E 选择器约定。 -->
# 平台测试治理说明

## 1. 测试分层

平台测试统一分为四层：

| 层级 | 目标 | 归属 |
| :--- | :--- | :--- |
| L0 单元/组件测试 | 校验纯函数、组件局部渲染、局部状态流 | `backend` / `editor` / `runtime` 各自项目 |
| L1 子项目集成测试 | 校验 API、状态流、预览构建、Runtime 壳层行为 | `backend` / `editor` / `runtime` 各自项目 |
| L2 跨模块契约测试 | 校验 `backend <-> runtime`、`editor <-> backend` 稳定协议 | 根仓 `tests/contracts/` |
| L3 平台 E2E 冒烟 | 校验登录、页面/组件/资源/主题/AI/构建等主链路 | 根仓 `tests/e2e/` |

默认原则：

- `runtime/` 维护自身测试；CI 与根 pnpm workspace 输入统一由主仓门禁管理。
- 根仓不复制 Runtime 私有实现测试，只做平台集成与委托校验。
- 第一阶段不设置统一覆盖率门槛，以关键套件通过为阻断条件。

## 2. 目录归属

### 根仓

```text
tests/
├── contracts/
│   ├── editor-backend/
│   └── runtime-backend/
└── e2e/
    ├── fixtures/
    ├── helpers/
    └── specs/
```

### Backend

```text
backend/tests/
├── api/
├── contracts/
├── fixtures/
├── integration/
└── unit/
```

### Editor

- 组件、工具函数、局部状态测试继续与源码同目录维护，文件命名为 `*.test.ts`
- 跨组件工作流测试命名为 `*.flow.test.ts`
- 公共测试支撑统一放在 `editor/src/test/`

### Runtime

- Runtime 单元测试与组件测试位于 `runtime/src/**/*.test.ts`
- 统一环境 mock 放在 `runtime/src/test/setup.ts`
- 完整门禁包含类型检查、测试与生产构建：`pnpm run test:runtime:gate`

## 3. 命令入口

根仓提供统一入口：

```bash
pnpm run test:backend
pnpm run test:backend:unit
pnpm run test:backend:api
pnpm run test:backend:integration
pnpm run test:editor
pnpm run test:editor:check
pnpm run test:editor:build
pnpm run test:editor:gate
pnpm run test:runtime
pnpm run test:runtime:gate
pnpm run test:contracts
pnpm run test:repository
pnpm run test:python-workspace
pnpm run test:contracts:docker-context
pnpm run test:render-contracts
pnpm run test:renderer
pnpm run test:render-e2e
pnpm run test:contracts:gateway
pnpm run test:contracts:cli-skill
pnpm run test:e2e:run
pnpm run test:e2e:prepare
pnpm run test:e2e
pnpm run test:e2e:regression
pnpm run test:e2e:all
pnpm run test:all
```

命令语义：

| 命令 | 语义 |
| :--- | :--- |
| `test:backend:*` | Backend pytest 分层入口，marker 由 `backend/tests/` 目录自动补齐。 |
| `test:editor` | Editor Vitest。 |
| `test:editor:check` | Editor 类型检查，执行 `vue-tsc -b`。 |
| `test:editor:build` | Editor 生产构建，执行 `vue-tsc -b && vite build`。 |
| `test:editor:gate` | Editor 质量门禁，执行 `check + test + build`。 |
| `test:runtime` | 只执行 Runtime 子项目 Vitest。 |
| `test:runtime:gate` | Runtime 子项目质量门禁，执行 `check + test + build`。 |
| `test:contracts` | 根仓跨模块契约测试，只收集 `tests/contracts/**/*.test.ts`。不同于 `backend/tests/contracts`。 |
| `test:contracts:gateway` | 真实 Nginx 网关契约回归（`scripts/contracts/test-gateway-openapi.py`）。 |
| `test:contracts:cli-skill` | CLI Skill 示例契约测试。 |
| `test:e2e:run` | 不准备数据，运行 `auth + smoke`；globalSetup 仍校验 Backend 与 smoke 数据指纹。 |
| `test:e2e:prepare` | 准备 E2E 环境：未显式设置 `TESTING_START_*`/`TESTING_REUSE_BACKEND` 时先校验端口与 E2E 依赖并注入自启环境变量，再重置/播种 smoke 数据并启动或确认服务。 |
| `test:e2e` | 平台 E2E smoke 默认入口，等价于 `test:e2e:prepare + test:e2e:run`。 |
| `test:e2e:regression` | 准备环境后运行 `visual-edit + ai + runtime-heavy`。 |
| `test:e2e:all` | 准备环境后运行全部 Playwright project。 |
| `test:all` | 本地全量入口：Backend 全部 marker + Editor gate + Runtime gate + 根仓 contracts + 渲染契约/Renderer + Python workspace 共装验证 + 全部 E2E project。脚本先校验端口与 E2E 依赖，再自动注入 `TESTING_START_*` 与 `AI_TEST_MODE=mock` 并自启服务，无需手动设置环境变量；端口被占用或依赖未启动时立即报错并给出提示。 |

辅助测试数据命令：

```bash
pnpm run test:seed:smoke
pnpm run test:reset:data
```

本地数据库与 Redis 运行态统一通过 `scripts/dev/compose.infra.yml` 启动：

```bash
docker compose -f scripts/dev/compose.infra.yml up -d
```

该 compose 文件只服务本地开发和 CI 测试基础设施，不属于 `deploy/` 下的交付部署模板；统一维护在 `scripts/dev/`。

Backend 测试默认把 `REDIS_URL` 设置为 `memory://test`，不依赖本机 Redis。手动联调预览、截图、代码检查或构建时必须启动 compose 中的 Redis；AI run/HITL 状态由 Backend 主库中的平台运行态表承担，不再依赖 Redis run hash 或 Redis stream。

AI run 状态切换后无需执行 Redis run 迁移脚本；旧 Redis run key 等待 TTL 自然过期。

## 4. 输出目录

测试报告和临时材料按用途分开：

| 路径 | 来源 | 说明 |
| :--- | :--- | :--- |
| `test-results/e2e/html-report/` | Playwright HTML reporter | E2E HTML 报告。 |
| `test-results/e2e/artifacts/` | Playwright `outputDir` | 失败 trace、截图、视频和 `.last-run.json`。 |
| `test-results/e2e/services/` | E2E 服务编排 | Backend、Editor、Runtime、Renderer 子进程日志。 |
| `backend/.pytest_cache/` | pytest | Backend 测试缓存，不是报告。 |
| `.tmp/` | 手动诊断脚本 | AI run 诊断、截图排障等人工材料。 |
| `backend/.tmp/` | Backend 本地调试 | LLM HTTP trace、本地 smoke DB 等运行态排障材料。 |

约束：

- 新增可持久化测试报告时优先放入 `test-results/<suite>/`。
- `test-results/e2e/storage-state.json` 包含认证 cookie，不得上传为 CI artifact。
- `.tmp/` 只放诊断或排障材料，不作为 CI 测试报告目录。
- 不再提交 `output.txt`、`test_output.txt`、`test_result.txt` 这类一次性终端输出文件。

## 5. 稳定测试选择器约定

以下节点允许并鼓励通过 `data-testid` 暴露稳定选择器：

- 登录表单、登录按钮
- 工作空间 / 项目 / 页面列表
- 页面预览 iframe
- 组件工作台与组件预览
- 资源上传 / 替换 / 详情
- 主题列表、字体列表、主题详情
- AI 侧栏、待确认态、结构化提问态
- 项目构建弹窗与构建历史

约束：

- 仅在平台主链路节点添加，不把 `data-testid` 扩散到所有基础组件。
- 优先保证语义稳定，避免绑定纯视觉类 class 名。

## 6. CI 策略

PR 必跑：

1. `backend`：`unit + api`
2. `editor`：`check + Vitest`
3. 根仓 `contracts`

条件执行：

- 当 `runtime/` 目录源码发生变化时，执行 `pnpm run test:runtime:gate`

全量测试执行时机：

- `main` 分支 push。
- 每周一 03:00（Asia/Shanghai）的定时任务。
- 手动触发 `.github/workflows/platform-test.yml` 且 `full_tests=true`。

`main` push 的 E2E 执行 `test:e2e`；每周定时和手动 `full_tests=true` 执行 `test:e2e:all`。Release 质量门禁同样执行 `test:e2e:all`。

全量测试范围：

1. `backend integration`
2. Runtime gate
3. 根仓分层 E2E（按触发类型运行 smoke 或 all）
4. 平台镜像 build smoke：构建 `web-presentation` 单镜像但不推送

全量流程中，`e2e` 冒烟依赖 Backend、Editor、contracts 和 Runtime 门禁通过后再启动；平台镜像 build smoke 依赖 `e2e` 冒烟通过后再启动，避免基础测试失败时继续执行重型任务。

Release 发布：

- GitHub Release `published` 后执行完整质量门禁。
- 编译并推送包含最新 Runtime 运行时能力的平台镜像及 Runtime 独立服务镜像。
- 构建并推送单个平台镜像 `web-presentation:<release_tag>`；稳定 Release 同时推送 `latest`。

定时、手动全量和 Release 覆盖可视化编辑、真实构建、截图与长链路 AI 测试。

## 7. 故障排查

### E2E 无法连接服务

优先确认：

1. `E2E_BASE_URL`
2. `E2E_API_BASE_URL`
3. `E2E_RUNTIME_BASE_URL`
4. 本地 PostgreSQL 是否已通过根目录 compose 启动
5. 本地 Redis 是否已通过根目录 compose 启动

### AI 冒烟不稳定

- E2E 默认应使用 `AI_TEST_MODE=mock`
- 不依赖真实 LLM 响应顺序、时延和内容

### Runtime 相关失败

- 从仓库根目录运行 `pnpm run test:runtime` 检查 Runtime 单元测试；需要类型检查、单元测试和生产构建时运行 `pnpm run test:runtime:gate`
- 若问题涉及 Runtime Kit、Backend 契约或平台集成，再运行对应的根仓契约与集成检查
- 若预览、代码检查或截图返回 artifact 缺失，优先确认 `REDIS_URL`、`REDIS_KEY_PREFIX` 与 Redis TTL 配置是否与 Backend 实例一致。

## 仓库边界与真实渲染验证

- `test:repository`：根契约测试的子集，校验文档本地链接、代码围栏、交付 Dockerfile 覆盖、Compose 文件位置、共享 workspace 的 CI 触发范围与环境覆盖逻辑。
- `test:python-workspace`：在全部 Python 成员共装后，从根目录、Backend、Renderer 分别导入 `app`、`wp_renderer`、`render_contracts`，并验证根目录诊断 CLI。
- `test:contracts:docker-context`：向 Docker 发送临时合成配置，验证所有模块的 `.env`、密钥与缓存不会进入构建上下文，示例文件仍可交付。
- `test:render-contracts` / `test:renderer`：纯契约与 Renderer 单元测试。
- `test:render-e2e`：准备 E2E 环境后运行真实页面截图 smoke，覆盖四服务链路并检查 PNG 文件头、尺寸与任务状态，不再使用 Renderer 目录的占位用例。

运行 E2E 前分别执行 `pnpm exec playwright install chromium` 与 `uv run --project renderer playwright install chromium`；Linux 首次安装加 `--with-deps`。准备脚本会启动/确认 Renderer，并使用 Backend 真实客户端校验服务认证、Worker ID 和 profile。测试凭据使用专门的 `E2E_RENDER_SERVICE_CREDENTIAL`，可通过 `E2E_RENDERER_BASE_URL` 覆盖 Renderer 地址，禁止复用生产身份。
