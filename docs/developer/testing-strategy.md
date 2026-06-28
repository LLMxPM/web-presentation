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

- `runtime/` 作为独立子项目，继续维护自身测试与 CI。
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

- Runtime 私有测试继续留在子模块仓库
- 统一环境 mock 放在 `runtime/src/test/setup.ts`

## 3. 命令入口

根仓提供统一入口：

```bash
pnpm run test:backend
pnpm run test:backend:unit
pnpm run test:backend:api
pnpm run test:backend:integration
pnpm run test:editor
pnpm run test:editor:check
pnpm run test:editor:gate
pnpm run test:runtime
pnpm run test:runtime:delegated
pnpm run test:runtime:gate
pnpm run test:contracts
pnpm run test:e2e:run
pnpm run test:e2e:prepare
pnpm run test:e2e
pnpm run test:all
```

命令语义：

| 命令 | 语义 |
| :--- | :--- |
| `test:backend:*` | Backend pytest 分层入口，marker 由 `backend/tests/` 目录自动补齐。 |
| `test:editor` | Editor Vitest。 |
| `test:editor:check` | Editor 类型检查，执行 `vue-tsc -b`。 |
| `test:editor:gate` | Editor 质量门禁，执行 `check + test`。 |
| `test:runtime` / `test:runtime:delegated` | 只委托执行 Runtime 子项目 Vitest。 |
| `test:runtime:gate` | Runtime 子项目质量门禁，执行 `check + test + build`。 |
| `test:contracts` | 根仓跨模块契约测试，只收集 `tests/contracts/**/*.test.ts`。不同于 `backend/tests/contracts`。 |
| `test:e2e:run` | 只执行 Playwright，不准备数据、不检查服务。 |
| `test:e2e:prepare` | 重置并播种 smoke 数据，然后检查或按环境变量启动 Backend、Editor、Runtime。 |
| `test:e2e` | 平台 E2E smoke 默认入口，等价于 `test:e2e:prepare + test:e2e:run`。 |
| `test:all` | 本地全量入口，包含 Backend、Editor gate、Runtime gate、根仓 contracts 和 E2E smoke。 |

辅助测试数据命令：

```bash
pnpm run test:seed:smoke
pnpm run test:reset:data
```

本地数据库与 Redis 运行态统一通过根目录 `docker-compose.dev.yml` 启动：

```bash
docker compose -f docker-compose.dev.yml up -d
```

该 compose 文件只服务本地开发和 CI 测试基础设施，不属于 `deploy/` 下的交付部署模板；移动它时需要同步更新文档和 `.github/workflows/*` 中的引用。

Backend 测试默认把 `REDIS_URL` 设置为 `memory://test`，不依赖本机 Redis。手动联调预览、截图、代码检查或构建时必须启动 compose 中的 Redis；AI run/HITL 状态由 Backend 主库中的平台运行态表承担，不再依赖 Redis run hash 或 Redis stream。

AI run 状态切换后无需执行 Redis run 迁移脚本；旧 Redis run key 等待 TTL 自然过期。

## 4. 输出目录

测试报告和临时材料按用途分开：

| 路径 | 来源 | 说明 |
| :--- | :--- | :--- |
| `test-results/e2e/html-report/` | Playwright HTML reporter | E2E HTML 报告。 |
| `test-results/e2e/artifacts/` | Playwright `outputDir` | 失败 trace、截图、视频和 `.last-run.json`。 |
| `backend/.pytest_cache/` | pytest | Backend 测试缓存，不是报告。 |
| `.tmp/` | 手动诊断脚本 | AI run 诊断、截图排障等人工材料。 |
| `backend/.tmp/` | Backend 本地调试 | LLM HTTP trace、本地 smoke DB 等运行态排障材料。 |

约束：

- 新增可持久化测试报告时优先放入 `test-results/<suite>/`。
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

- 当 `runtime` 子模块 SHA 发生变化时，执行 `pnpm run test:runtime:gate`

全量测试执行时机：

- `main` 分支 push。
- 每周一 03:00（Asia/Shanghai）的定时任务。
- 手动触发 `.github/workflows/platform-test.yml` 且 `full_tests=true`。

全量测试范围：

1. `backend integration`
2. Runtime gate
3. 根仓 `e2e` 冒烟
4. 平台镜像 build smoke：构建 `web-presentation` 单镜像但不推送

全量流程中，`e2e` 冒烟依赖 Backend、Editor、contracts 和 Runtime 委托校验通过后再启动；平台镜像 build smoke 依赖 `e2e` 冒烟通过后再启动，避免基础测试失败时继续执行重型任务。

Release 发布：

- GitHub Release `published` 后执行完整质量门禁。
- 校验当前 `runtime` 子模块 SHA 对应的 Docker Hub 镜像 `web-runtime-vue:sha-<12位sha>` 已存在。
- 构建并推送单个平台镜像 `web-presentation:<release_tag>`；稳定 Release 同时推送 `latest`。

夜间或手动执行：

- 扩展 E2E 回归
- 截图 / PDF / 打印 / 长链路 AI 测试

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

- 先在 `runtime/` 仓库单独执行 `pnpm check && pnpm test && pnpm build`
- 再回到根仓排查跨模块契约或平台集成问题
- 若预览、代码检查或截图返回 artifact 缺失，优先确认 `REDIS_URL`、`REDIS_KEY_PREFIX` 与 Redis TTL 配置是否与 Backend 实例一致。
