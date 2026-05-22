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
pnpm run test:editor
pnpm run test:runtime:delegated
pnpm run test:contracts
pnpm run test:e2e
pnpm run test:all
```

辅助测试数据命令：

```bash
pnpm run test:seed:smoke
pnpm run test:reset:data
```

本地数据库与 Redis 运行态统一通过根目录 `docker-compose.dev.yml` 启动：

```bash
docker compose -f docker-compose.dev.yml up -d
```

Backend 测试默认把 `REDIS_URL` 设置为 `memory://test`，不依赖本机 Redis。手动联调预览、截图、代码检查、AI 后台 run 或构建时必须启动 compose 中的 Redis；Redis 不可用会在启动期或调用运行态能力时给出明确错误，避免出现任务已经执行但事件或 artifact 丢失的半可用状态。

Redis 运行态上线前应在维护窗口执行 `uv run python -m app.scripts.prepare_redis_runtime_cutover`。默认模式只检查旧 `AiAgentRunTask/AiAgentRunEvent`，存在 `pending/running/cancelling` 会返回非 0；确认切换时使用 `--migrate-paused` 迁移 paused run，必要时再追加 `--force-cancel-active` 强制收敛旧 active run。

## 4. 稳定测试选择器约定

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

## 5. CI 策略

PR 必跑：

1. `backend`：`unit + api + integration`
2. `editor`：Vitest
3. 根仓 `contracts`
4. 根仓 `e2e` 冒烟

条件执行：

- 当 `runtime` 子模块 SHA 发生变化时，执行 `pnpm --dir runtime test`

夜间或手动执行：

- 扩展 E2E 回归
- 截图 / PDF / 打印 / 长链路 AI 测试

## 6. 故障排查

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
