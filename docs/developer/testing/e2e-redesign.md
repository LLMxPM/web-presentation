<!-- 文件功能：提出平台 E2E 冒烟套件重设计提案，覆盖问题盘点、目标架构、实施阶段与验收标准。 -->
# E2E 冒烟套件重设计提案

## 1. 背景：现状问题盘点

平台 E2E 位于 `tests/e2e/`，共 8 个 spec、12 个用例。当前存在五类问题，均已在本地完整运行中实际观察到：

### 1.1 用例与 UI 结构漂移

- `ai-visual-tools.smoke.spec.ts` 断言 `agent-sidebar-panel` 内存在「内容助手」tab 且 `aria-selected=true`，但合并助手后 `AgentGlobalSidebar.vue` 已是单助手布局、不存在 tab 栏，用例稳定失败。
- 用例断言 `details.tool-call-group`、`details.visual-tool-details` 等私有 class，违反《平台测试治理说明》第 5 节「优先语义稳定，避免绑定纯视觉类 class 名」的既有约定。

### 1.2 内联 API stub 与真实契约漂移

- `ai-visual-tools.smoke.spec.ts` 内联约 300 行 `/api/ai/**` route stub（agents/sessions/attachments/runs/stream/runtime 快照），字段结构与 Backend 真实响应完全手工复制。
- stub 数据在 spec 内自洽，但 Backend 契约一改，spec 不会失败也不会更新，属于「虚假绿」测试。
- 用例同时混用真实 API（页面、项目、资源）与桩 API（AI），失败时无法确定是哪一层的问题。

### 1.3 冷启动抖动

- 首次完整运行时 9/12 用例失败，全部卡在 `loginAsAdmin`：Backend 首个登录请求约 2.3s，随后 Editor Vite 冷编译 AdminLayout 模块图，5s 断言窗口内 URL 未离开 `/login`；后 3 个用例因模块缓存而通过。
- 已补充 `globalSetup` 预热（登录 + 进入工作空间首页）缓解，但只解决登录与首页链路的冷编译。

### 1.4 用例间共享可变数据

- smoke 数据由 `test:seed:smoke` 一次性注入，但 `pages-preview.smoke.spec.ts` 的可视化编辑用例会真实修改页面内容（复制/删除循环项、改字重、换资源），刷新后断言依赖这些改动后的状态。
- 用例执行顺序与数据状态强耦合：重跑、单独跑、乱序跑结果不一致；一次失败后数据被半改，后续运行的前提不可复现。

### 1.5 定位成本高

- 断言默认 5s 超时，在并行 8 worker 的冷/热环境差异下不稳定。
- 失败产物（trace/截图/视频）已按 `test-results/e2e/artifacts/` 落盘，但没有统一断言网络层契约或捕获 Backend 日志，问题归属（前端/后端/数据）需要人工翻 trace。

## 2. 重设计目标与原则

1. **契约真实**：AI 用例优先走真实 Backend；需要确定性的部分由 Backend 侧 `AI_TEST_MODE=mock` 提供，不在浏览器层伪造 API。
2. **结构稳定**：断言只依赖语义角色、`data-testid` 和用户可见文案，禁止依赖私有 class 与已废弃 UI 结构。
3. **数据自愈**：每个用例（或每组用例）不依赖其它用例留下的数据状态；重置/播种按场景执行。
4. **冷启动免疫**：服务编排阶段完成预热，用例窗口内不承担编译与建连成本。
5. **分层演进**：smoke 核心链路保持轻量快跑，长链路（构建、截图、复杂 AI）通过独立 Playwright project 和命令运行，不依赖目录或标签的隐式约定。
6. **运行环境可识别**：执行浏览器用例前必须确认 Backend 连接 E2E 数据库、使用 E2E Redis 且启用了 AI mock，不能把“端口可达”视为测试环境就绪。
7. **失败可诊断**：失败产物除 trace、截图和视频外，还应包含失败 API 摘要、服务日志，以及 AI 用例对应的 `run_id/session_id` 诊断信息。

## 3. 目标架构

```text
tests/e2e/
├── global-setup.ts          # 登录预热 + storageState 生成（已有，扩展）
├── fixtures/
│   ├── ai-cases.ts          # E2E 输入、场景 ID 与用户可见期望，不包含 Backend 执行逻辑
│   └── test-data.ts         # 用例级实体夹具与 teardown
├── helpers/
│   ├── auth.ts              # loginAsAdmin（已有，超时放宽）
│   ├── navigation.ts        # 导航助手（已有）
│   ├── diagnostics.ts       # 失败 API、AI run 与服务日志附件
│   └── selectors.ts         # 少量跨 spec 的主链路语义定位器
└── specs/
    ├── smoke/               # 核心链路：登录、列表页、预览、构建入口（轻量）
    ├── visual-edit/         # 可视化编辑（自带数据夹具，独立数据库场景）
    ├── ai/                  # AI 用例（依赖 Backend mock 场景）
    └── runtime-heavy/       # 真正执行截图、构建等重型链路

backend/app/ai/testing/
├── scenario_protocol.py     # 场景、状态匹配、响应和错误的类型契约
├── agent_function_model.py  # 内容助手工具调用与 deferred 恢复
├── vision_function_model.py # 图片理解模型的确定性结构化输出
├── scenarios.py             # 根据不可变输入与消息历史生成下一步响应
└── image_adapter.py         # 返回固定合法 PNG 的图片生成适配器
```

依赖方向固定为 `tests/e2e -> Backend API`。Backend 运行时代码不得读取 `tests/e2e/`；E2E fixture 只引用双方约定的场景 ID，不承载 Backend 响应脚本。

### 3.1 数据策略

| 场景 | 数据来源 | 说明 |
| :--- | :--- | :--- |
| smoke 核心链路 | `test:seed:smoke` 全局播种 | 只读型用例：列表、详情、预览、入口可见性 |
| 可视化编辑 | 用例级数据夹具 | 每个用例创建独立项目/页面，写操作不污染全局 smoke 数据 |
| AI 用例 | Backend mock 场景 | 模型层确定性输出，会话/运行/工具调用全部走真实 API 与真实持久化 |

实现说明：

- `pages-preview.smoke.spec.ts` 中 3 个写型可视化编辑用例改为「fixture 内创建专属项目/页面（通过真实 API），teardown 最佳努力归档」，删除对全局 Smoke Project 的修改依赖。
- 全局 smoke 数据保持只读约束，任何写型用例不得触碰。
- 测试实体名称包含 `workerIndex + UUID`，创建过程中立即记录实体 ID，保证并行执行不冲突、部分创建失败后仍可清理。
- fixture 不在 setup 扫描并归档整个 E2E namespace，避免不同 worker 或并行 project 误归档彼此的活动项目。唯一名称保证历史残留不影响后续断言；完整 `test:e2e:*` 由 prepare 重置数据，连续 `test:e2e:run` 依靠唯一实体与 teardown 保持可重复。
- fixture teardown 通过 Playwright fixture 或 `try/finally` 执行。归档失败应作为附件记录，但不得覆盖原始测试失败。

### 3.2 登录复用

- `globalSetup` 中登录一次，保存 `storageState` 到 `test-results/e2e/storage-state.json`；写入前显式创建父目录。
- 时序约束：storageState 必须在 `test:e2e:prepare`（reset + seed + 启动服务）之后生成，因此放在 Playwright `globalSetup` 内（当前预热逻辑保留为同一阶段）。
- 普通 smoke、visual-edit 和 AI project 使用该状态；auth project 显式配置空 `storageState`，同时覆盖「未登录重定向」和「登录成功」。不要依赖用例内部临时清 cookie 来维持隔离。
- 保留 `loginAsAdmin` 供 auth project 和定向调试使用；普通已登录用例不再重复登录。
- `storage-state.json` 是包含认证 cookie 的敏感临时文件：允许 Playwright 读取，但必须被 Git 忽略，且不得作为 CI artifact 上传。第 3.7 节的脱敏约束仅针对诊断附件、服务日志和报告摘要，不禁止 storageState 自身保存认证状态。

### 3.3 AI 数据策略：真实 Backend + Backend 侧 mock

现状：`AI_TEST_MODE=mock` 只短路 Runtime 代码诊断；模型调用仍走真实供应商协议，seed 的「Mock 凭证」实际无法完成一次对话。

目标：在 Backend 增加确定性 mock 能力，分两层：

1. **内容助手模型 mock**：保留真实 Chat `provider_key` 与调用协议的一一对应关系，不新增可持久化或可披露的 `provider_key="mock"`。`seed:smoke` 创建 `e2e-mock-agent-*` 模型配置；仅当 `AI_TEST_MODE=mock` 且 model ID 命中该前缀时，runner/resolver 才注入内容助手 `FunctionModel`。阶段 2 先支持普通对话和视觉工具 `analyze_visuals` → `generate_image` 链路。
2. **图片理解模型 mock**：图片理解槽位单独绑定 `e2e-mock-vision-*` Chat 模型配置，注入只负责图片理解结构化输出的 `FunctionModel`。不能继续让内容助手与图片理解槽位共用同一 E2E Chat 配置，否则 `analyze_visuals` 内部的嵌套模型调用无法区分。
3. **图片生成 mock**：保留 `provider_key="openai_image"`；图片生成槽位绑定 `e2e-mock-image-*` 配置，在 mock 模式下注入测试适配器，返回固定、格式合法的小型 PNG 并继续走真实资源落库链路，不发起 HTTP 调用。

`AI_TEST_MODE` 只负责启用测试安全门，不负责选择单个全局场景。`tests/e2e/fixtures/ai-cases.ts` 为每个内容助手场景提供唯一、固定的自然语言输入；Backend mock registry 根据模型角色和规范化后的初始用户输入选择场景，未知输入立即返回明确测试错误。实现不得使用进程级调用计数器或可变的全局 `E2E_AI_SCENARIO`，从而允许多个场景并行执行及 deferred run 自动恢复。

mock 模式启动时设置 Pydantic AI `ALLOW_MODEL_REQUESTS=False`，任何没有被测试 resolver 接管的模型请求应立即失败，防止错误配置意外访问真实供应商。不得向 `/ai/providers` 增加 mock provider，也不得通过正常业务 API在非 E2E 数据库中创建或选择 `e2e-mock-*` 模型；场景 ID 不属于公开供应商目录契约。

场景执行逻辑收敛在 `backend/app/ai/testing/`；`tests/e2e/fixtures/ai-cases.ts` 只保存场景 ID、用户输入和用户可见期望。浏览器侧不再拦截 `/api/ai/**`。

#### 3.3.1 FunctionModel 场景协议

内容助手场景使用代码定义的有类型状态机，不使用仅靠数组下标推进的脚本。每个场景至少声明：

- `scenario_id`、适用的 `model_role`、唯一初始输入匹配器和最终用户可见期望。
- 一组 transition；每项包含当前状态匹配器、期望工具名、参数匹配/提取逻辑、期望 tool return 或 deferred result Schema，以及下一次 `ModelResponse` 构造器。
- 明确的终态和未知状态错误。错误需包含 `scenario_id`、模型角色、已观察到的工具名和脱敏后的消息种类摘要，不包含完整用户内容。

状态只能从 FunctionModel 本次收到的 `ModelMessage`（包括续跑后投影出的 tool return）和 `AgentInfo` 推导，不能写入进程级可变状态，也不能假设 FunctionModel 能直接读取平台的 `DeferredToolResults` 对象。相同历史必须生成相同响应，使重复恢复具备幂等性。FunctionModel 只模拟模型决策；工具参数仍经过真实 Pydantic Schema 校验，业务工具、任务入队、持久化、Batch 协调和 deferred result 回灌均走平台真实代码。

首批场景的最小状态流为：

```text
普通对话：initial → final_text

视觉链路：initial
  → call analyze_visuals
  → receive real visual-analysis tool return
  → call generate_image
  → receive real deferred image result after background continuation
  → final_text
```

`generate_image` 用例必须覆盖真实 `waiting_external → running → completed` 恢复。页面创建/结构化编辑对应的 `ai_page_mutation_jobs` 不作为阶段 2 的前置范围；需要覆盖时新增独立 `page-mutation` 场景，不扩张首批视觉场景的状态机。

#### 3.3.2 `AI_TEST_MODE` 既有行为与新增行为

mock 模式下三条能力彼此独立，不互相替代：

| 调用链 | mock 行为 | 是否进入 FunctionModel |
| :--- | :--- | :--- |
| Runtime 代码诊断 | 保留 `RuntimeDiagnosticsClient` 现有通过结果短路 | 否 |
| 内容助手 / 图片理解 | 分别注入 agent / vision FunctionModel | 是 |
| 图片生成供应商 | 注入固定 PNG 测试适配器 | 否 |

FunctionModel 不需要感知 Runtime 诊断上下文。短场景应配置足够的上下文预算，确保不意外触发历史压缩；未来若需要覆盖压缩流程，应增加独立模型角色和场景，不能让压缩调用误入内容助手状态机。

替代方案（不采纳）：浏览器侧 route stub。原因：无法暴露 Backend 会话/运行态真实契约，且 300 行桩已证明漂移成本高于收益。

### 3.4 服务编排、环境指纹与预热

- `test:e2e:prepare` = reset 数据 → seed 场景 → ensure-services（按 `TESTING_START_*` 启动/复用）→ 预热（并入 globalSetup）。
- Backend 在 `AI_TEST_MODE=mock` 下通过 `/api/testing/e2e-readiness` 提供不含连接串和密钥的测试就绪信息，至少返回 `test_mode=mock`、`database_profile=e2e`、`redis_profile=e2e`、`seed_version`、`smoke_data_ready` 和 mock scenario 版本；非 mock 模式下该入口返回 404。
- `ensure-services.mjs` 先等待 `/api/auth/me` 返回 401/200，再校验测试就绪信息。任一指纹不匹配立即失败，不能继续使用该 Backend。
- 新启动的 Backend 必须由 `buildE2eBackendEnv()` 注入环境。复用现有 Backend 仅在测试指纹完全匹配时允许，不能因端口可达自动复用开发服务。
- Editor 与 Runtime 继续做 HTTP 就绪检查；预热至少覆盖登录、工作空间首页和首个页面详情入口，不要求遍历所有业务页面。
- `test:e2e:run` 定位为不修改数据的开发调试命令，假设此前已经完成 prepare；globalSetup 仍必须检查 `seed_version` 与 `smoke_data_ready`。前置数据缺失时应快速失败，并提示执行 `pnpm run test:e2e:prepare`，不能进入业务页面后才失败。

### 3.5 断言与稳定性约定

- `playwright.config.ts` 增加 `expect.timeout: 15_000`、`actionTimeout: 10_000`，用例级特殊等待显式传参。
- 禁止在 spec 内使用 `details.*`、`.tool-call-group` 等私有 class；视觉工具卡片改为语义化 `data-testid`（`visual-tool-card`、`visual-status-region`），由 Editor 补齐后用例引用。
- AI 用例对「运行结果」只断言用户可见产物（图片、文案、已保存提示），不断言事件序列的私有结构。
- 15s 是默认上限，不替代就绪检查。纯 UI 同步反馈优先使用更短的局部超时，预览、AI、构建等明确异步边界单独放宽。

### 3.6 Playwright project 与命令边界

`playwright.config.ts` 显式定义以下 project，不能只靠目录重命名或 `@regression` 标签表达默认范围：

| Project | 目录/范围 | 默认 `test:e2e` |
| :--- | :--- | :--- |
| `auth` | 无 storageState 的登录与重定向 | 是 |
| `smoke` | 登录后只读核心链路和构建入口 | 是 |
| `visual-edit` | 独立夹具的真实写入链路 | 否 |
| `ai` | Backend mock 下的真实会话、run、工具和图片链路 | 否 |
| `runtime-heavy` | 真正执行截图刷新、项目构建和产物校验 | 否 |

`auth` 与 `smoke` 不声明 Playwright project dependency：storageState 由 globalSetup 生成，不是 auth project 的产物；两者允许并行执行。普通 project 只共享只读 storageState 文件，不共享 BrowserContext。

命令语义固定为：

```text
test:e2e:run         只运行 auth + smoke，不准备环境
test:e2e             prepare 后运行 auth + smoke
test:e2e:regression  prepare 后运行 visual-edit + ai + runtime-heavy
test:e2e:all         prepare 后运行全部 project
```

CI 命令按现有测试治理收敛为：

| 触发场景 | E2E 命令 | 说明 |
| :--- | :--- | :--- |
| Pull Request | 不运行 E2E | 保持当前 unit、api、Editor gate 和 contracts 门禁，不在本提案中扩大 PR 策略 |
| `main` push | `test:e2e` | 运行 auth + smoke；后续如耗时满足预算可单独评审升级为 all |
| 每周定时 | `test:e2e:all` | 覆盖 visual-edit、AI 和 Runtime 重型链路 |
| 手动 `full_tests=true` | `test:e2e:all` | 与定时全量门禁一致 |
| Release | `test:e2e:all` | 发布前覆盖全部 project |

阶段 4 必须同步修改 `.github/workflows/platform-test.yml`、`.github/workflows/platform-release.yml`、`docs/developer/testing/strategy.md`、`docs/developer/testing/commands.md` 和 `docs/developer/testing/e2e-smoke.md`。workflow 上传 `test-results` 时必须排除 `test-results/e2e/storage-state.json`。不得让 `playwright test` 的默认“运行所有 project”行为改变脚本语义。

### 3.7 失败诊断

- fixture 监听 `requestfailed` 以及 `/api/**` 的 5xx 响应，失败时附加 URL、方法、状态码、响应错误码和截断后的错误摘要；诊断附件、服务日志和报告摘要不得保存认证 cookie、API Key 或完整用户内容。storageState 按第 3.2 节单独管理，不上传为报告产物。
- `ensure-services.mjs` 启动的 Backend、Editor、Runtime 日志统一写入 `test-results/e2e/services/`，保留控制台摘要。
- AI fixture 记录本用例创建的 `session_id/run_id`。AI 用例失败时调用只读 `diagnose_ai_run` CLI，把 summary 作为 Playwright attachment 保存；诊断失败只追加说明，不覆盖原始失败。
- 保留现有 trace、截图和视频策略，所有产物继续收敛在 `test-results/e2e/`。

### 3.8 Backend mock 契约测试矩阵

阶段 2 必须至少覆盖以下组合，不能只验证一条成功路径：

| 条件 | 预期 |
| :--- | :--- |
| `AI_TEST_MODE=disabled` + `e2e-mock-*` | 不注入测试模型/适配器，readiness 返回 404 |
| `AI_TEST_MODE=mock` + 普通 model ID | 不静默替换；真实模型请求被 `ALLOW_MODEL_REQUESTS=False` 阻止 |
| mock + `e2e-mock-agent-*` | 只注入内容助手 FunctionModel |
| mock + `e2e-mock-vision-*` | 只注入图片理解 FunctionModel，并返回符合业务 Schema 的结构化结果 |
| mock + `e2e-mock-image-*` | 只注入图片生成测试适配器，不发起 HTTP |
| 非 E2E 数据库创建或绑定 `e2e-mock-*` | 业务服务拒绝 |
| readiness 数据库、Redis、seed 或场景版本不匹配 | `ensure-services` 失败，不进入 Playwright |
| 未知场景、未知 transition 或缺失 deferred call ID | 明确失败，禁止回退真实模型 |
| 同一历史重复请求/恢复 | 响应一致，不重复产生不可幂等副作用 |

## 4. 实施阶段

| 阶段 | 内容 | 阻塞点 |
| :--- | :--- | :--- |
| 1 | 记录当前 auth + smoke 冷启动/热重跑耗时基线；修复 `ai-visual-tools.smoke.spec.ts` 两个用例；补齐视觉卡片 `data-testid`；stub 从 spec 内联迁到 `fixtures/ai-stub/` 临时公共模块，禁止继续新增 stub 路由 | Editor 小改动，可立即做 |
| 2 | Backend 有类型场景协议、agent/vision FunctionModel、图片测试适配器、真实模型请求熔断、既有 Runtime 诊断兼容和测试环境指纹；完成第 3.8 节契约矩阵 | Backend 改动；不得新增公开 `mock` provider |
| 3 | AI 用例切换为真实 API；storageState 与 auth project；用例目录和 Playwright project 分层；写型用例改用可清理的独立夹具 | 依赖阶段 2 |
| 4 | 默认/回归命令与 CI workflow、测试文档收敛；超时与耗时对比；失败 API、服务日志和 AI run 自动诊断 | 阶段 3 全量通过后进入 |

阶段 1 只负责恢复临时稳定基线，不代表 AI 契约真实化完成；临时 stub 必须在阶段 3 删除。阶段 2 是安全、可并行的 Backend mock 基础；阶段 3 完成数据和 API 真实性迁移；阶段 4 固化门禁语义与诊断能力。

## 5. 验收标准

1. `pnpm test:e2e` 与 `pnpm test:e2e:all` 在冷启动和热重跑下分别连续两次全绿。
2. `ai-visual-tools.smoke.spec.ts` 不再出现 tab 断言与私有 class 断言；spec 内不再内联 300 行 stub。
3. 写型用例与全局 smoke 数据解耦：单独跑、乱序跑、并行跑结果一致；强制在用例中途失败后再次运行仍可通过。
4. AI 用例在 `AI_TEST_MODE=mock` 下走真实 Backend 会话/运行链路，浏览器侧无 `/api/ai/**` 拦截。
5. mock 模式下真实模型网络请求被全局禁止；正常供应商目录不增加 mock provider，非 E2E 环境不能选择 `e2e-mock-*` 模型。
6. `ensure-services` 对指向开发数据库、关闭 mock 或使用非 E2E Redis 的 Backend 明确失败，不进入浏览器用例。
7. 默认 `test:e2e` 只收集 auth + smoke；`test:e2e:regression` 和 `test:e2e:all` 的收集数量通过 `--list` 契约测试固定。
8. 未登录重定向、登录成功两条 auth 断言仍然覆盖，且 auth project 不加载全局 storageState。
9. 人为制造一个 API 500 和一个 AI run 失败时，报告中分别包含失败 API 摘要、服务日志以及 AI run 诊断附件。
10. `test:e2e:run` 在 smoke 数据未准备时于 globalSetup 快速失败，并给出 prepare 命令；数据已准备时不执行 reset/seed。
11. agent、vision、image 三类 mock 按 model ID 独立分派；视觉场景真实经历一次 deferred 暂停与后台恢复，重复恢复不产生第二份资源或重复终态事件。
12. 阶段 1 和阶段 4 分别执行至少 3 次冷启动、3 次热重跑，记录 auth + smoke 的中位耗时；若阶段 4 中位数增长超过 20%，需在合入前说明原因或优化。

## 6. 风险与取舍

- **Backend mock 模型层成本**：FunctionModel 必须覆盖工具调用、deferred result 回灌和恢复后的消息历史。若短期不可行，公共浏览器 stub 只能作为阶段 1 临时基线；真实模型 + 固定提示词仅允许手动验证，不进入门禁，也不能长期保留“虚假绿”的 AI E2E。
- **测试代码进入 Backend 包**：`backend/app/ai/testing/` 会随 Backend 代码发布，但只能在 `AI_TEST_MODE=mock` 下导入和执行；需要测试证明 disabled 模式入口不可达、目录不披露、真实模型请求不被误替换。
- **storageState 与 reset 时序**：globalSetup 先通过环境指纹确认服务，再登录并保存状态；auth project 始终无状态。`test:e2e:run` 不执行 reset，因此 fixture 自身仍需支持连续调试。
- **视觉产物确定性**：mock 图片生成返回固定尺寸、固定颜色、格式合法的 PNG，断言真实资源保存和展示链路，不做像素级比较。
- **E2E 全量时长**：默认 auth + smoke 维持 8-12 个轻量用例；visual-edit、ai 和 runtime-heavy 通过独立 project 和显式命令运行，收集边界由 `--list` 测试保护。
