<!-- 文件功能：项目顶层说明文档，介绍平台愿景、架构设计、模块边界、开发方式与子项目协作规则。 -->
# Vue 云端可视化构建平台

这是一个面向 Vue 组件开发与可视化编排场景的云端构建平台规划仓库。项目目标是提供一套可私有化部署的 Web IDE + Runtime + Backend 协作体系，让用户可以在浏览器内完成组件编写、组合预览、动态构建与产物交付。

当前仓库采用 Monorepo 组织方式，其中 `runtime/` 不是普通目录，而是独立项目 `web-runtime-vue` 的 Git 子模块接入目录。也就是说，这个仓库负责承载平台级集成与协作边界，而 `web-runtime-vue` 负责承载预览底座，并通过模式切换同时支持“独立项目形态”和“平台运行时形态”。

平台测试现已统一为四层：

1. 子项目内部维护 L0 单元/组件测试。
2. 子项目内部维护 L1 集成测试。
3. 根仓 `tests/contracts/` 维护 L2 跨模块契约测试。
4. 根仓 `tests/e2e/` 维护 L3 平台级 Playwright smoke。

统一规则、目录归属和 CI 入口见 [docs/testing-strategy.md](./docs/testing-strategy.md)。

## 1. 项目目标

平台围绕以下四个核心目标设计：

1. 极速预览体验：代码保存后，通过 Runtime 驱动 Vite HMR，让 Iframe 预览窗口在 500ms 级别内完成热更新。
2. 数据持久化安全：代码、配置、历史版本统一存储于数据库，运行容器只保留可丢弃的运行时缓存。
3. 动态编排与打包：支持用户选择多个 Vue 页面或组件，动态生成入口并执行生产构建，输出标准化 Zip 产物。
4. 环境高可用与自愈：Runtime 在依赖变更或严重错误时可通过容器重启机制恢复，重新拉取现场并继续服务。

## 2. 总体架构

系统采用“控制面 + 数据面”解耦模式：

- Backend：控制中枢，负责数据持久化、任务调度、产物托管。
- Runtime：执行引擎，负责初始化拉取、HMR 驱动、动态构建与压缩回传。
- Editor：用户操作界面，负责代码编辑、保存、构建触发与预览呈现。
- AI Gateway：Backend 基于 Agno 直接构建智能体，以 `session_id`、Redis 后台 run 运行态、Redis Stream 事件回放与 Agno session/run 协同管理会话状态，通过泛化 scope BFF 为 Editor 提供统一智能体、组件助手、用户级大模型管理、图片输入、页面截图视觉读取、工具鉴权与 HITL 暂停恢复；页面与项目能力由统一智能体按用户工具配置直接启用，仅在模型不支持图片输入时隐藏截图视觉工具。
- Infra：通过 Docker / Docker Compose 负责服务编排、网络隔离与容器自愈。

### 技术选型

| 模块 | 角色 | 技术选型 | 说明 |
| :--- | :--- | :--- | :--- |
| Backend | 控制面 / 数据持久化 | Python 3.10+ / FastAPI | PostgreSQL 保存业务事实，Redis 保存短期运行态，SQLAlchemy 2.0(async)、httpx、BackgroundTasks |
| Runtime（web-runtime-vue） | 预览引擎 / 构建车间 | Node.js 18+ / Vite Core API | 以 Vite 插件机制承载双模式能力：独立编辑模式 + 平台运行时模式 |
| Editor | 前端工作台 | Vue 3 / Vite | Monaco Editor、Element Plus、Tailwind CSS |
| Infra | 编排与部署 | Docker / Docker Compose | `restart: always`、容器网络隔离 |

## 3. 仓库结构

```text
web-presentation/
├── README.md
├── AGENTS.md
├── .gitmodules
├── package.json       # 根仓测试编排入口
├── docker-compose.dev.yml
├── docs/
│   └── testing-strategy.md
├── tests/
│   ├── contracts/
│   └── e2e/
├── backend/          # Backend 服务，负责接口、任务调度、数据存储
├── editor/           # Editor 工作台，负责代码编辑与预览编排
└── runtime/          # Runtime 子项目（Git Submodule）
```

### 模块边界说明

#### backend/

计划承载以下职责：

- 多用户登录、会话与平台用户管理
- 工作空间成员隔离下的工作空间、项目、页面资源库增删改查
- 工作空间级资源库、组件库、主题库与样式库统一主数据管理；样式库仅作为展示配置、主题 key 和 Markdown 样式规范的复用模板，应用到项目时复制字段，不建立关联；样式库支持离线 Zip 导入导出，导出选中样式时会携带其引用主题、主题资源与字体配置
- 读取 Runtime Kit manifest，并在页面源码、工作空间组件源码与 previewSchema 中校验 `@runtime-kit` / `@workspace-components` 导入边界；工作空间组件路径保持 `@workspace-components/<component_code>/v/<version_no>`，源码默认导入名由组件 `import_name` 提供
- 基于 `backend/app/ai/tool_specs.py` 维护智能体工具、工具组、调用格式与返回示例的单一事实源，并派生 Agent 配置页目录、Agno Function 元数据和统一智能体运行时工具装配策略
- 基于 PostgreSQL 的数据持久化
- 为后续 Runtime 协议、资源管理与版本能力预留扩展空间

#### editor/

计划承载以下职责：

- 用户登录页、账户设置页与平台管理员用户管理页
- 工作空间、项目、页面资源库管理页
- 工作空间主题库与样式库管理页，以及项目/组件预览的主题选择、项目样式规范编辑和应用工作空间样式入口
- 基于表格、表单和弹窗的后台 CRUD 交互
- 为后续资源中心与 Runtime 接入保留导航与状态管理骨架

#### runtime/

`runtime/` 是独立项目 `web-runtime-vue` 在当前仓库中的接入目录，不在本仓库内从零维护。它会作为平台运行时底座持续演进，并通过子模块方式同步到当前仓库。

Runtime 维护页面可引用基础能力的公开契约：`runtime/src/runtime-kit/manifest/runtime-kit.manifest.json` 是 Backend 校验 `page_content`、工作空间组件源码与组件预览 schema 的单一事实源。页面和工作空间组件只能通过 `@runtime-kit/...` 引用 Runtime 基础组件、composable、工具和类型；Runtime shell、component-preview 宿主页及其辅助类型/组合式能力、PDF 导出、布局侧栏、Toast、ErrorBoundary 等壳层能力不进入该清单，也不进入智能体能力目录。


如果你需要了解 `web-runtime-vue` 的内部能力、开发脚本、页面系统或已有功能，请优先阅读：

- [runtime/README.md](./runtime/README.md)
- [runtime/AGENTS.MD](./runtime/AGENTS.MD)

## 4. 目标业务流程

以下流程是平台目标态流程，不代表当前仓库已经全部落地。

### 4.1 代码保存与热更新

1. 用户在 Editor 中保存代码。
2. Editor 调用 Backend 保存接口。
3. Backend 写入数据库。
4. 当用户显式发起文件上传时，Editor 调用 Backend 的独立 Runtime 文件接口，将页面源码按指定文件名推送到 Runtime 指定目录。
5. Backend 再为该 Runtime 页面文件生成一个带短时票据的独立预览链接，供 Editor 的 Iframe 访问。
6. Runtime 基于文件路径直接渲染 Vue 页面，并对 `src/views/日期/用户ID/` 目录下的页面模块做票据鉴权。
7. Vite 监听到文件变更后触发 HMR，Editor 中的 Iframe 自动完成预览刷新。

### 4.2 依赖变更与环境自愈

1. 用户修改 `package.json` 或其他关键依赖配置。
2. Backend 持久化后向 Runtime 发起重启任务。
3. Runtime 主动退出进程。
4. Docker 基于 `restart: always` 自动拉起新容器。
5. 新容器重新安装依赖、全量拉取代码并恢复服务。
6. Editor 通过健康检查感知恢复完成并撤销遮罩层。

### 4.3 动态选件构建与产物回传

1. 用户在 Editor 勾选多个页面或组件并发起构建。
2. Backend 创建任务并调度 Runtime 开始构建。
3. Runtime 动态生成临时入口文件并调用 `vite build`。
4. Runtime 将构建产物压缩为 Zip 并上传回 Backend。
5. Backend 通过统一对象存储保存产物，并返回稳定的下载或静态访问地址；S3 模式下公开代理由 Backend 按需读取 Zip 后返回目标文件内容。

## 5. web-runtime-vue 协作方式

### 命名约定

为避免“项目名”和“目录名”混用，本文档统一采用以下约定：

- `web-runtime-vue`：指独立项目本身。
- `runtime/`：指 `web-runtime-vue` 在当前 Monorepo 中的子模块目录路径。
- `Runtime`：指平台架构中的运行时角色。

由于 `runtime/` 对应的是独立项目 `web-runtime-vue`，这个仓库建议遵循下面的协作策略：

1. 平台级说明写在顶层：整体架构、模块分工、接口协作、环境编排放在当前仓库维护。
2. `web-runtime-vue` 内部说明写在子项目：运行时实现细节、页面系统、模式切换策略、开发规范优先写入子项目自身文档。
3. 若存在跨仓库协议变更，需同步更新顶层 README、接口文档和部署说明，避免控制面与数据面理解不一致。

推荐的同步流程如下：

1. 在 `web-runtime-vue` 上游仓库完成能力开发与验证。
2. 提交并推送 Runtime 更新。
3. 回到当前仓库更新 `runtime` 子模块指向的新提交。
4. 如有接口、环境变量、启动方式变化，同步更新当前仓库文档。



## 6. 当前仓库状态

截至当前版本：

- `runtime/` 已作为独立项目 `web-runtime-vue` 的 Git 子模块接入，并有独立可运行内容。
- `backend/` 已完成页面管理一期后台基线：FastAPI、SQLAlchemy 2.0(async)、Alembic、多用户登录、工作空间成员隔离、工作空间/项目/页面 CRUD，以及独立 Runtime 文件上传接口基线。
- `backend/` 现已内嵌基于 Agno 的智能体运行时，注册 `agent-coordinator`、`component-manager` 与 `resource-manager` 三个稳定入口；智能体会话链路改为 session-first：Editor 围绕 `session_id` 工作，Backend 以 `ai_agent_run_tasks` 作为 active-run 主状态源，并把规范化事件持久化到 `ai_agent_run_events` 供断线后回放。
- 智能体 HITL 支持工具确认与结构化单选提问：工具确认和 `ask_user` 提问都会暂停 Agno run，Editor 在输入区覆盖展示确认或逐题选择界面，再通过 active-run continue/cancel 恢复或取消。
- 智能体 SSE 连接现在只是事件订阅，不再决定 run 生命周期；切换会话、离开路由或关闭面板不会取消后台 run，回到会话后通过 `active-run` 和 `runs/{run_id}/events/stream` 恢复运行状态与结果。
- 智能体运行中的停止按钮会先调用后端取消接口，状态进入 `cancelling` 后等待 Agno 的优雅取消事件；若超过兜底窗口仍未终态，前端会提供强制结束动作，由后端以 `force=true` 释放当前 session 占用。
- `backend/` 新增全局/个人大模型管理能力：管理员维护全局模型与全局默认槽位，用户可选择全局模型但不能修改，也可维护自己的个人模型；运行时按用户槽位绑定优先、全局默认兜底解析模型。
- `backend/` 已为智能体补充图片输入链路：模型配置显式声明是否支持图片输入，用户可在会话中上传不超过 10MB 的 png/jpg/jpeg/webp 图片；页面截图视觉工具只允许传 `page_id`，由后端校验工作空间/项目边界并返回当前版本最新截图。
- `backend/` 新增用户级智能体配置能力：智能体入口保持系统内置，不提供启用开关；用户可在账户层编辑智能体描述、业务补充提示词、内容助手 Team 成员描述、查看工具目录、关闭业务工具并覆盖工具说明，运行时按统一工具规格、用户配置与模型图片能力合成 Agno Agent/Team。
- `backend/app/ai/tool_specs.py` 是智能体工具目录的单一事实源：工具 key、分组、说明、风险级别、确认要求、上下文要求、调用参数 schema 的来源关系与返回示例都应从这里派生或登记；`agent_catalog`、`tools/disclosure.py` 与组件管理工具注册不应再单独维护重复工具清单。
- `editor/` 的账户 AI 设置页已展示面向 Agent 的完整工具说明，包括当前生效说明、系统默认说明、参数 JSON Schema、调用示例、返回示例、上下文要求和运行时披露组；这些调用契约与返回示例为系统只读，用户可编辑智能体描述、业务补充提示词、内容助手 Team 成员描述、工具说明和工具提示词。
- `editor/` 已完成页面管理一期管理后台基线：Vue 3、Vue Router、Pinia、Element Plus、工作空间/项目/页面 CRUD 页面与账户设置页，并支持将页面文件推送到 Runtime 后以内嵌 Iframe 方式预览；全局左侧智能体侧边栏现作为统一入口，默认进入总控智能体，在组件库路由可切换到组件助手。
- `runtime/` 已补充 Backend 可调用的内网文件接口基线，用于受控目录内的文件 CRUD 与批量上传。
- Runtime 预览态页面文件当前统一落在 `src/views/日期/用户ID/` 目录下，并通过独立 `/__preview` 入口按文件路径直接渲染，而不是依赖业务路由。
- 工作空间现已提供与资源库、组件库并列的主题库；主题主数据在工作空间层维护颜色、字体绑定、Logo 与项目图标，项目配置与组件预览默认配置通过 `theme_key` 引用主题。
- 工作空间现已提供与资源库、组件库、主题库并列的样式库；样式记录包含展示配置、可选主题 key 与 Markdown 纯文本样式规范，应用到项目时只复制字段，项目不保存 `style_id` 或 `style_key` 关联，因此后续修改样式库不会影响已配置项目。样式库离线包以选中样式为根，自动携带被引用主题、主题 logo / 项目图标资源与字体配置；导入时先预检，同 key 内容一致复用，内容不同则拒绝导入。当前离线包 schema 为 v2，不兼容旧 v1 包。
- 项目页面展示配置统一维护页面宽高、基础字号和默认描边宽度；这些规格随 `app.config.yaml` 的 `app.page` 下发，不再属于主题。Icon 默认尺寸跟随基础字号，局部尺寸通过 Tailwind `size-*` 或 `h-* w-*` 类控制。
- 项目样式配置现已包含 Markdown 纯文本样式规范，供 Editor 编辑与内容助手生成页面时参考；Runtime 不消费该字段。
- 内容助手上下文、项目样式读写工具与工具规格已纳入项目样式规范，并提供只读的工作空间样式、组件使用和资源使用查询工具；应用样式仍通过确认型项目样式写入工具复制到项目配置，不建立样式关联。
- Runtime 在预览与未来构建态统一通过 Backend 配置接口在线拉取 `app/icons/routes/themes`；其中临时预览、代码检查、组件预览与截图预览 artifact 已改由 Redis 保存，构建 snapshot 与历史产物仍以 PostgreSQL 为准。`themes.config.yaml` 既可以读取 legacy `theme_config_yaml`，也可以根据 `theme_key` 动态组装，但新主题配置不再输出字号与图标默认规格。
- 项目级路由现已改为由 Editor 通过 UI 编排并以 Backend 结构化数据存储；Runtime 预览/发布时所需的 `component` 路由结构由 Backend 动态组装下发，不再依赖手写 `routes.config.yaml`。
- 当前一期仍未覆盖完整资源中心、Dashboard、项目与页面关联使用关系，以及 Runtime 反向回传 Backend。
- 根目录提供了 `docker-compose.dev.yml` 作为本地 PostgreSQL 与 Redis 开发入口。Redis 不保存 Agno 长期历史、截图 PNG、构建 zip 或页面/组件业务事实，只保存 Agent run、SSE 事件、预览 artifact、截图锁与构建心跳等正在发生的运行态。

## 7. 本地测试入口

推荐先在仓库根目录准备开发数据库与 Redis：

```powershell
docker compose -f .\docker-compose.dev.yml up -d
```

Redis 运行态切换维护窗口前，可在 `backend/` 下执行旧 active run 检查；默认发现 `pending/running/cancelling` 会阻断，确认切换时再显式迁移 paused 或强制取消 active：

```powershell
uv run python -m app.scripts.prepare_redis_runtime_cutover
uv run python -m app.scripts.prepare_redis_runtime_cutover --migrate-paused
uv run python -m app.scripts.prepare_redis_runtime_cutover --force-cancel-active --migrate-paused
```

根仓统一测试入口：

```powershell
pnpm install
pnpm run test:backend
pnpm run test:editor
pnpm run test:runtime:delegated
pnpm run test:contracts
pnpm run test:e2e
```

平台 smoke 数据 CLI：

```powershell
pnpm run test:reset:data
pnpm run test:seed:smoke
```



## 8. 许可证说明

当前仓库 `web-presentation` 顶层内容采用 Apache License 2.0，见 [LICENSE](./LICENSE)。

需要特别注意：

- 顶层 `LICENSE` 仅覆盖当前仓库顶层维护的代码与文档。
- `runtime/` 是独立项目 `web-runtime-vue` 的 Git 子模块，继续遵循它自身仓库内声明的许可证。
- 在当前工作区中，`web-runtime-vue` 的许可证文件位于 [runtime/LICENSE](./runtime/LICENSE)。


## 9. 参考文档

- Runtime 项目说明：[runtime/README.md](./runtime/README.md)
- Runtime 协作说明：[runtime/AGENTS.MD](./runtime/AGENTS.MD)
