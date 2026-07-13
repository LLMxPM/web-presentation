<!-- 文件功能：仓库级开发协作说明文档，约束开发者与智能代理在 web-presentation 中的模块边界、编码规范、测试要求和文档维护方式。 -->
# AGENTS.md

本文档面向在 `web-presentation` 仓库内工作的开发者与智能代理。目标是让 Backend、Editor、Runtime、AI 工具体系和部署文档在同一组约束下演进，避免接口漂移、运行态耦合和重复元数据。

## 1. 基础协作规范

- 使用中文进行协作、提交说明和项目文档编写。
- 单个代码文件应控制行数；当文件职责过多、分支复杂或测试难以聚焦时，优先拆分模块。
- 每个源代码文件开头应包含文件功能描述，Markdown 文件除外。
- 为函数补充中文注释，优先解释职责、输入输出和关键约束，避免重复代码字面含义。
- 前端使用 `pnpm` 管理依赖；Python 项目使用 `uv` 管理依赖，并使用 `venv` 管理虚拟环境。
- 项目通常已经启动，不要反复启动服务；需要确认运行态时先查看现有进程、端口或文档说明。
- 可能存在用户未提交改动；不要回滚、覆盖或格式化无关文件。

## 2. 仓库定位

`web-presentation` 是面向 AI 演示文稿创作的平台集成仓库，不是单一前端项目。平台面向 PPT、图文卡片、报告页等内容形态，把页面内容代码化，并围绕资源、组件、主题、样式和 Runtime 能力进行抽象复用。

当前仓库负责：

- 维护 Backend、Editor、Runtime 的模块边界与接口契约。
- 承载平台级数据模型、AI Agent、工具规格、预览构建链路和部署模板。
- 通过 `runtime/` Git 子模块接入独立项目 `web-runtime-vue`。
- 沉淀开发、测试、部署、CI/CD 和 Runtime 子模块协作规则。

当前已落地登录、多用户隔离、工作空间/项目/页面管理、资源库、组件库、主题库、样式库、AI Agent 会话、工具确认、预览、截图、构建和容器发布；跨项目资产治理、Dashboard、项目/页面使用关系运营视图和 Runtime 反向回传仍在建设中。

## 3. 目录职责

### 顶层目录

- `README.md`：面向最终用户，说明产品定位、核心能力、典型流程、部署入口和文档导航。
- `AGENTS.md`：面向开发者与智能代理，说明仓库内修改边界、编码规范、测试要求和文档维护规则。
- `docs/`：承载平台文档中心，按 `user/` 用户文档、`developer/` 开发文档和 `assets/` 图片资源拆分。
- `deploy/`：承载外部依赖简化版、内置依赖简化版、production env 版 compose 模板和部署环境变量示例。
- `tests/`：承载根仓跨模块契约测试和 E2E smoke。

### backend/

Backend 是平台控制面，负责用户、权限、工作空间、项目、页面、资源、组件、主题、样式、AI Agent、预览 artifact、构建任务和产物托管。

开发约束：

- 新增 Python 代码时按 `api/routes`、`schemas`、`models`、`repositories`、`services`、`ai` 等现有分层放置，不要把路由、模型、仓储和业务逻辑写进同一个文件。
- 新增或调整接口契约时，先明确路径、入参、出参、权限和错误语义，再联动 Editor、Runtime 或测试。
- 涉及资源、组件、页面源码和 previewSchema 的导入能力时，必须经过 Backend 侧边界校验。
- Backend 默认项目配置模板由 `backend/app/config_templates/` 自身维护；不要在 Backend 运行时代码中直接读取 `runtime/public/config/`。Runtime 自带的 `public/config/*.config.yaml` 仅作为 Runtime 独立运行和本地 fixture 使用，根仓契约测试只约束两侧模板入口和必要结构。
- 涉及 Pydantic AI 新特性或不确定用法时，先查阅官方文档再确定实现方式。

### backend/app/ai

AI 目录承载 Pydantic AI 智能体、平台自有会话运行态、工具注册、工具披露、上下文构造和用户级 AI 配置。工具实现使用平台自有工具对象，再由 Pydantic AI runner 装配为运行时 Tool；新增运行态能力应落在平台运行态表和 Pydantic AI runner 上。

AI run 排障优先使用只读诊断 CLI：

```powershell
uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <run_id> --format summary
uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <run_id> --format json
uv run --project backend python -m app.scripts.diagnose_ai_run --session-id <session_id> --format summary --output .tmp/ai-session-diagnostics.txt
```

该脚本从根仓运行时会自动补读 `backend/.env`，但不会覆盖已存在的环境变量。它只查询 `ai_agent_*` 表，按 run 或 session 输出状态、事件序列、工具调用、pending/resolved requirement、消息摘要和 Pydantic AI `message_history_json` 摘要；不得在脚本中修改 run、requirement、tool call 或 Redis 状态。`run_id/session_id` 不存在时应返回非 0 退出码。需要修复历史坏数据时，应另写限定范围的一次性维护脚本，不要扩展诊断 CLI 做写操作。

`backend/app/ai/tool_specs.py` 是智能体工具目录、工具组、风险级别、确认要求、上下文要求、调用格式与返回示例的单一事实源。新增、删除或调整智能体工具时必须先更新该规格，再由规格派生：

- `agent_catalog.py`
- `tools/disclosure.py`
- 组件管理工具注册
- `/ai/agent-catalog`
- `/ai/agent-configs`
- Editor 中展示给用户的工具说明和 `agent_guide`

不要在其它文件复制第二份工具清单、工具分组或返回示例。调整工具参数、确认要求、风险级别、上下文要求或返回结构时，应同步更新防漂移测试。

页面创建与结构化编辑属于重资源写工具：必须通过 `ai_page_mutation_jobs` 持久化队列执行，不能在 Pydantic tool 调用中直接并发运行 Runtime/Chromium。页面工具的 deferred result 由后台 Batch 协调器自动恢复；修改该流程时必须同时检查租约、取消、页面版本复核、SSE `waiting_external` 状态和自动续跑测试。截图任务与页面渲染诊断共享 Chromium 池，任何新增浏览器调用都必须接入该池，不能自行启动无上限的浏览器实例。

### editor/

Editor 是创作工作台，负责登录、工作空间、项目、页面、组件、资源、主题、样式、AI 侧边栏、账户 AI 设置、预览 iframe 和构建入口。

开发约束：

- 新增前端能力时，按现有习惯拆分视图、组件、组合式逻辑、状态和 API 请求层。
- UI 变更应优先复用 `components/ui`、`components/project`、`components/agent` 等现有组件和交互模式。
- 账户 AI 设置页应展示面向 Agent 的完整工具说明，包括当前生效说明、系统默认说明、参数 JSON Schema、调用示例、返回示例、上下文要求与运行时披露组。
- 工具调用契约和返回示例是系统只读信息；用户只允许编辑智能体描述、智能体提示词、工具说明和工具提示词。

### runtime/

`runtime/` 是独立项目 `web-runtime-vue` 在当前仓库中的接入目录，不是根仓普通子目录。修改 Runtime 时要同时考虑它的独立项目形态和平台运行时形态。

Runtime 负责：

- 基于 Vue/Vite 的页面预览、组件预览、截图、诊断和构建。
- 维护 `src/runtime-kit/manifest/runtime-kit.manifest.json`，作为 Backend 校验页面源码、工作空间组件源码和 previewSchema 可导入能力的公开清单。
- 提供版本化 `@runtime-kit` 公共能力，供页面源码、工作空间组件和 AI 生成内容使用。

Runtime Kit 约束：

- 清单项必须使用 `<ExportName>.v<整数版本>` 命名，并指向带 `.vN` 的公开 import path。
- 页面源码、工作空间组件源码与 previewSchema 不允许引用未带 `.vN` 的 `@runtime-kit` 公开路径。
- 需要不兼容演进时新增 v2/v3 文件，不修改仍被依赖的旧版本文件。
- Runtime shell 内部组件、component-preview 宿主页及其辅助类型/组合式能力、PDF 导出、侧栏/缩略图、Toast 与 ErrorBoundary 不应通过 `@runtime-kit` 暴露给页面源码、工作空间组件源码或智能体能力目录。

## 4. 测试与验证

优先运行与改动范围匹配的最小测试集，并在最终说明中写清楚已运行和未运行的测试。

常用入口：

```powershell
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
pnpm run test:e2e
```

测试入口语义：

- `test:editor` 只执行 Editor Vitest；需要 Editor 类型检查与测试门禁时使用 `test:editor:gate`。
- `test:runtime` / `test:runtime:delegated` 只委托 Runtime 子项目 Vitest；需要 Runtime 完整门禁时使用 `test:runtime:gate`。
- `test:contracts` 是根仓跨模块契约测试，不等同于 Backend 自身的 `backend/tests/contracts`。
- `test:e2e:run` 只执行 Playwright；`test:e2e` 会先重置并播种 smoke 数据、确认服务，再执行 Playwright。
- E2E 报告和失败产物统一写入 `test-results/e2e/`。

涉及以下范围时应特别补充验证：

- AI 工具规格、披露组或前端工具说明变化：补充防漂移测试，确保工具 key、运行时 Tool、披露工具组和 `agent_guide` 一致。
- Runtime Kit manifest 或公开 import path 变化：补充 Backend 契约测试和 Runtime manifest 测试。
- 预览、截图、构建、资源引用或 Runtime 回源变化：补充相关 integration、contract 或 E2E smoke。
- 认证、权限、工作空间隔离变化：补充多用户访问或 API 权限测试。

## 5. 文档维护规则

出现以下情况时，同步更新顶层 `README.md`：

- 产品定位、核心能力、典型用户流程或最终用户理解路径发生变化。
- 平台模块职责、架构关系、部署入口或文档导航发生变化。

出现以下情况时，同步更新顶层 `AGENTS.md`：

- 开发协作规范、编码约束、测试要求或文档约束发生变化。
- Backend、Editor、Runtime、AI 工具体系或子模块修改策略发生变化。

出现以下情况时，优先更新 `docs/developer/` 下专题文档：

- 本地开发、测试数据、部署、CI/CD 或测试策略发生变化。
- 接口契约尚未稳定但需要跨模块联调，应先在文档中声明请求路径、入参、出参和错误语义。

出现以下情况时，优先更新 `docs/user/` 下用户文档：

- 用户理解路径、平台使用流程、AI 协作方式、项目状态路线或面向使用者的功能说明发生变化。
- 新增或替换文档配图、截图和占位图时，图片资源应统一放在 `docs/assets/`。

出现以下情况时，优先更新 `web-runtime-vue` 自身文档：

- Runtime 新增开发命令、目录结构、插件系统、构建机制、页面体系或 Runtime Kit 能力。
- Runtime 内部编码规范、页面开发方式或独立项目运行方式发生变化。

## 6. 命名约定

- `web-presentation`：当前平台集成仓库。
- `web-runtime-vue`：独立 Runtime 项目名称。
- `runtime/`：`web-runtime-vue` 在当前仓库中的 Git 子模块路径。
- `Runtime`：平台架构中的预览与构建执行角色。
- `Editor`：面向用户的创作工作台。
- `Backend`：平台控制面服务。
