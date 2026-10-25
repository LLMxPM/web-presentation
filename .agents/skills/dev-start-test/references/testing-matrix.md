# 测试命令与验证矩阵

本文件是 `dev-start-test` 技能的测试执行参考，承接原 `AGENTS.md` 测试章节的命令、入口语义、按改动补测映射和交付前验证。`AGENTS.md` 只保留“按本技能选择最小充分测试集并汇报”的总体要求。

## 1. 常用命令与语义

### Backend

```bash
pnpm run test:backend          # 全部 marker
pnpm run test:backend:unit
pnpm run test:backend:api
pnpm run test:backend:integration
pnpm run test:backend:pg-claim
pnpm run test:backend:runtime-state-parity
```

- Backend 测试默认 `REDIS_URL=memory://test`，不依赖 Redis。
- `test:backend:pg-claim` 执行 PostgreSQL 认领形态与双库迁移对拍；提供 `P4_POSTGRES_DATABASE_URL` 时跑真实 PG，CI 以 `P4_POSTGRES_REQUIRED=1` 强制缺配置失败。
- `test:backend:runtime-state-parity` 校验 Runtime 状态适配契约。
- `test:lite:runtime-state-drill` 执行 lite 运行态演练（不在 `test:all` 内）。

### Editor

```bash
pnpm run test:editor
pnpm run test:editor:check
pnpm run test:editor:build
pnpm run test:editor:gate      # check + test + build
```

### Runtime

```bash
pnpm run test:runtime
pnpm run test:runtime:gate     # check + test + build
```

### 根仓契约、仓库与 workspace

```bash
pnpm run test:contracts                  # 根仓跨模块契约，不等于 backend/tests/contracts
pnpm run test:repository                 # 文档链接、部署边界、环境覆盖
pnpm run test:python-workspace           # 全成员共装环境、包解析与根目录 CLI
pnpm run test:contracts:docker-context   # 合成配置验证 Docker 排除规则
pnpm run test:contracts:compose-images   # compose 镜像契约
pnpm run test:contracts:gateway          # 真实 Nginx 网关契约回归
pnpm run test:contracts:cli-skill        # CLI Skill 示例契约
pnpm run test:contracts:generated        # codegen 漂移检查
```

- HTTP DTO 修改后先运行 `pnpm run codegen:editor-api`，必要时运行 `codegen:preview-types` / `codegen:model-view-types`，再运行 `test:contracts:generated`。
- `test:repository` 检查文档链接、部署边界和环境覆盖，并运行 `dev-*.test.ts` 中的停服规划、命令入口、E2E 预检与地址隔离测试；改 AGENTS/技能后优先运行。

### Renderer 与渲染契约

```bash
pnpm run test:render-contracts
pnpm run test:renderer
pnpm run test:render-e2e
```

- `test:render-contracts` 运行 `packages/render-contracts` 契约单测；`test:renderer` 运行 Renderer 单测。
- `test:render-e2e` 先准备 E2E 环境，再运行基础页面真实截图 smoke，覆盖 Backend→Renderer→Runtime 和 PNG 下载；三维模型像素截图在 `runtime-heavy` project。必须安装 Node/Python 两套 Playwright Chromium。

### E2E

```bash
pnpm run test:e2e:prepare
pnpm run test:e2e:run      # auth + smoke，不重置数据
pnpm run test:e2e          # prepare + auth + smoke
pnpm run test:e2e:regression
pnpm run test:e2e:all
pnpm run test:seed:smoke
pnpm run test:reset:data
```

- `test:e2e:run` 只执行 Playwright，假设 prepare 已完成；globalSetup 仍校验 Backend 与 smoke 数据指纹。
- `test:e2e` 会重置并播种 smoke 数据、确认服务，再执行 Playwright。
- 默认 project：auth + smoke；扩展回归：visual-edit + ai + runtime-heavy；全部 project：`test:e2e:all`。
- 三维模型真实像素截图在 `runtime-heavy/model3d-screenshot.spec.ts`；已准备好 E2E 环境时，可用 `pnpm exec playwright test --config tests/config/playwright.config.ts --project=runtime-heavy model3d-screenshot.spec.ts` 定向验证。
- E2E 服务拓扑包含 Backend、Editor、Runtime、Renderer；报告与失败产物写入 `test-results/e2e/`。
- E2E 使用独立数据库（库名含 `_e2e`）、Redis DB 15 和 `AI_TEST_MODE=mock`；`prepare` 会重置并播种 E2E 数据。
- 每次重新 prepare 前必须先停 Backend，再让 prepare 启动；复用运行中的 Backend 可能因数据重置停止后台执行器。`prepare-e2e.mjs --stop-services` 已内置该顺序，并在副作用前拒绝禁用自启、非 mock 或 `TESTING_REUSE_BACKEND=true` 等冲突配置。
- 准备完成后运行 `test:e2e:run`；全部 project 使用 `pnpm exec playwright test --config tests/config/playwright.config.ts`，定向重跑追加 `--project=...`。这些命令不重置数据。`test:e2e:all` / `test:e2e:regression` 会再次 prepare，不用于直接复用已启动的环境。
- `TESTING_REUSE_BACKEND=true` 不应与数据重置混用；只执行 Playwright 时不需要设置该变量，globalSetup 会校验指纹。
- 首次运行安装 Node 与 Renderer 两套 Chromium。

## 2. `test:all` 阶段与未覆盖门禁

`pnpm run test:all` 是主全量门禁，固定执行：

```text
test:backend
→ test:editor:gate
→ test:runtime:gate
→ test:contracts
→ test:render-contracts
→ test:renderer
→ test:python-workspace
→ test:e2e:all
```

行为：

- 未配置时注入 `TESTING_START_*` 与 `AI_TEST_MODE=mock`，不需要手工设置；技能包装器会提前拒绝继承的冲突值。
- 启动前要求服务端口空闲；`assert-ports-free.mjs` 只检查 127.0.0.1，技能包装脚本会额外检查 `::1`。
- 任一阶段失败立即中止，后续阶段视为未运行，退出码透传。
- 最后的 E2E 阶段会重置并播种 `_e2e` 数据，结束后保留 E2E 服务。
- 不包含下列专项门禁，按改动补跑：

| 改动范围 | 补跑命令 |
|---|---|
| 文档链接、部署边界、环境覆盖 | `test:repository` |
| Docker 构建上下文 | `test:contracts:docker-context` |
| compose 镜像契约 | `test:contracts:compose-images` |
| Gateway / External API 契约 | `test:contracts:gateway` |
| CLI Skill 示例契约 | `test:contracts:cli-skill` |
| codegen 漂移 | `test:contracts:generated` |
| PostgreSQL 认领与双库迁移 | `test:backend:pg-claim` |
| Runtime 状态适配 | `test:backend:runtime-state-parity` |
| lite 运行态演练 | `test:lite:runtime-state-drill` |
| 真实截图链路 | `test:render-e2e` |
| 本地多副本架构演练 | `scripts/testing/docker-architecture.py` |
| 上一正式版镜像升级与旧产物回读 | `scripts/testing/docker_architecture_release_upgrade.py`、`scripts/testing/docker_architecture_release_artifact.py` |

推荐用 `full-test.mjs` 执行全量：它先做依赖与 IPv4/IPv6 端口预检、可选停服/装浏览器，再调用 `pnpm run test:all`。

## 3. 按改动补测映射

- **AI 工具规格、披露组或前端工具说明**：补充防漂移测试，确保工具 key、运行时 Tool、披露工具组和 `agent_guide` 一致。
- **Runtime Kit manifest 或公开 import path**：补充 Backend 契约测试和 Runtime manifest 测试。
- **预览、截图、构建、资源引用或 Runtime 回源**：补充相关 integration、contract 或 E2E smoke；三维模型渲染改动另补 `runtime-heavy/model3d-screenshot.spec.ts`。
- **认证、权限、工作空间隔离**：补充多用户访问或 API 权限测试。
- **HTTP DTO / OpenAPI**：运行 codegen 后执行 `test:contracts:generated`，并联动 Editor/Runtime/契约测试。
- **DB 方言、写冲突、后台任务认领**：补充 `test:backend:unit`、`test:backend:integration` 与 `test:backend:pg-claim`。
- **Renderer / 渲染契约**：运行 `test:render-contracts`、`test:renderer`；涉及真实渲染链时补 `test:render-e2e`。
- **文档、部署、仓库边界**：运行 `test:repository`；涉及 Docker/compose 时补对应契约测试。
- **CLI/Gateway 契约**：运行 `test:contracts:gateway` 与 `test:contracts:cli-skill`。
- **跨多端或发布前**：运行 `pnpm run test:all`，再按上表补未覆盖门禁。

## 4. 专项环境与交付前验证

### 本地多副本架构演练

使用 `scripts/testing/docker-architecture.py`，必须创建专属数据库、Redis、卷和回环端口，不能复用开发数据。阶段操作按依赖串行执行，结束后仅清理本项目；命令与证据边界见 [本地 Docker 架构演练](../../../../docs/developer/testing/docker-architecture-drill.md)。

上一正式版升级先在同一专属项目完成旧版 `seed`、`browser-same`、`pipeline` 和 `browser-build`，记录镜像 digest 与旧 ZIP 摘要，再用 `docker_architecture_release_upgrade.py` 排空业务容器、运行候选迁移并核对实际镜像；`docker_architecture_release_artifact.py` 经候选 Backend 重读原 ZIP 并在浏览器加载。若迁移已完成但本机就绪探针超时，只能在核对 revision 和实际容器后使用 `--resume` 续验，不能重跑升级或重置数据库。并行启动多套完整演练会占用较多 Docker Desktop 资源，按项目串行验收并分别 `cleanup`。

### E2E 环境

- 端口：8000/5173/7373/7400 必须空闲；同时检查 IPv4 与 IPv6。
- 依赖：默认本机 `_e2e` 数据库与 Redis DB 15；可用 `E2E_DATABASE_URL`/`E2E_REDIS_URL` 覆盖。
- 首次运行安装两套 Playwright Chromium；E2E 报告与失败产物在 `test-results/e2e/`。
- 预览域断言不得依赖系统 DNS：`preview.localhost` 只在浏览器内按 `*.localhost` 约定解析到回环地址，Playwright `ApiRequestContext` 会 `getaddrinfo ENOTFOUND`。需要产物响应头时在预览页内同源 `fetch`；prepare 预检会提示 hosts 修复方式。
- 结束或切换到开发环境前，先停止 E2E 服务，再按开发流程启动。

### 交付前验证

- E2E 必须覆盖远程截图实际产物，不以按钮可见或占位断言代替。
- 交付 Dockerfile 必须纳入镜像构建、实际启动与发布矩阵。
- 修改 Gateway 或 External API 契约时，运行真实 Nginx 回归 `pnpm run test:contracts:gateway`（或 `python scripts/contracts/test-gateway-openapi.py`）；发布后从外部 Gateway 使用 `scripts/contracts/check-gateway-openapi.py` 验证契约 JSON，不能以 HTTP 200 或 Backend 直连替代。
- CLI 请求契约失败直接报错，不引入离线契约或缓存降级。

## 5. 汇报与产物

- 最终说明必须写清楚：实际运行的命令、通过/失败数量、失败摘要、未运行项及原因。
- 全量测试失败时报告失败阶段与退出码，后续阶段标记为未运行；不要跳过失败阶段直接重跑全量。
- 服务日志：开发服务在 `.tmp/dev-logs/`；E2E 服务在 `test-results/e2e/services/`。
- E2E 报告与失败产物：`test-results/e2e/html-report/`、`test-results/e2e/artifacts/`。

## 6. 相关文档

- [平台测试治理说明](../../../../docs/developer/testing/strategy.md)
- [E2E 冒烟套件重设计](../../../../docs/archive/developer-work-2026-10/e2e-redesign.md)
- [本地 Docker 架构演练](../../../../docs/developer/testing/docker-architecture-drill.md)
