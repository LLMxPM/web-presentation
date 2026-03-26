<!-- 文件功能：项目顶层说明文档，介绍平台愿景、架构设计、模块边界、开发方式与子项目协作规则。 -->
# Vue 云端可视化构建平台

这是一个面向 Vue 组件开发与可视化编排场景的云端构建平台规划仓库。项目目标是提供一套可私有化部署的 Web IDE + Runtime + Backend 协作体系，让用户可以在浏览器内完成组件编写、组合预览、动态构建与产物交付。

当前仓库采用 Monorepo 组织方式，其中 `runtime/` 不是普通目录，而是独立项目 `PPT-Engineering` 的 Git 子模块接入目录。也就是说，这个仓库负责承载平台级集成与协作边界，而 `PPT-Engineering` 负责承载预览底座，并通过模式切换同时支持“独立项目形态”和“平台运行时形态”。

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
- Infra：通过 Docker / Docker Compose 负责服务编排、网络隔离与容器自愈。

### 技术选型

| 模块 | 角色 | 技术选型 | 说明 |
| :--- | :--- | :--- | :--- |
| Backend | 控制面 / 数据持久化 | Python 3.10+ / FastAPI | PostgreSQL、Tortoise ORM、httpx、BackgroundTasks |
| Runtime（PPT-Engineering） | 预览引擎 / 构建车间 | Node.js 18+ / Vite Core API | 以 Vite 插件机制承载双模式能力：独立编辑模式 + 平台运行时模式 |
| Editor | 前端工作台 | Vue 3 / Vite | Monaco Editor、Element Plus |
| Infra | 编排与部署 | Docker / Docker Compose | `restart: always`、容器网络隔离 |

## 3. 仓库结构

```text
web-presentation/
├── README.md
├── AGENTS.md
├── .gitmodules
├── backend/          # Backend 服务，负责接口、任务调度、数据存储
├── editor/           # Editor 工作台，负责代码编辑与预览编排
└── runtime/          # Runtime 子项目（Git Submodule）
```

### 模块边界说明

#### backend/

计划承载以下职责：

- 文件与 YAML 配置的增删改查
- 保存历史快照与版本记录
- 保存后异步触发 Runtime 同步
- 触发依赖安装、环境重启、构建导出等任务
- 接收并托管 Runtime 回传的构建产物

#### editor/

计划承载以下职责：

- 集成 Monaco Editor 提供代码编辑体验
- 承载文件树、组件选件、构建操作等 UI
- 通过 Iframe 接入 Runtime 实时预览
- 监听后端状态并在 Runtime 重启时展示 Loading 与恢复提示

#### runtime/

`runtime/` 是独立项目 `PPT-Engineering` 在当前仓库中的接入目录，不在本仓库内从零维护。它会作为平台运行时底座持续演进，并通过子模块方式同步到当前仓库。

`PPT-Engineering` 不是单一形态项目，而是建议逐步演进为双模式 Runtime：

##### standalone 模式

面向 `PPT-Engineering` 独立项目使用，保留当前已有的本地开发和可视化编辑能力：

- 本地文件管理与开发态文件读写
- Monaco 编辑器与分屏预览
- 主题、路由、图标、资源等配置编辑能力
- 基于 Vite 的本地 HMR 与静态构建

##### platform-runtime 模式

面向当前平台接入，作为 `PPT-Engineering` 在平台中的运行时模式，逐步补齐以下能力：

- 容器启动后的全量初始化拉取
- 接收内部同步指令并覆盖写盘
- 借助 Vite 的文件监听与 HMR 完成实时刷新
- 根据任务动态生成入口并执行构建
- 压缩 `dist` 并回传给 Backend
- 通过内部鉴权与容器重启机制实现受控执行与自愈

如果你需要了解 `PPT-Engineering` 的内部能力、开发脚本、页面系统或已有功能，请优先阅读：

- [runtime/README.md](./runtime/README.md)
- [runtime/AGENTS.MD](./runtime/AGENTS.MD)

## 4. 目标业务流程

以下流程是平台目标态流程，不代表当前仓库已经全部落地。

### 4.1 代码保存与热更新

1. 用户在 Editor 中保存代码。
2. Editor 调用 Backend 保存接口。
3. Backend 写入数据库并异步通知 Runtime 执行文件同步。
4. Runtime 根据文件标识从 Backend 拉取最新内容并写入本地运行目录。
5. Vite 监听到文件变更后触发 HMR。
6. Editor 中的 Iframe 自动完成预览刷新。

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
5. Backend 存储产物并返回下载或静态访问地址。

## 5. PPT-Engineering 双模式协作方式

### 命名约定

为避免“项目名”和“目录名”混用，本文档统一采用以下约定：

- `PPT-Engineering`：指独立项目本身。
- `runtime/`：指 `PPT-Engineering` 在当前 Monorepo 中的子模块目录路径。
- `Runtime`：指平台架构中的运行时角色。
- `platform-runtime`：指 `PPT-Engineering` 面向平台接入时的运行模式。

由于 `runtime/` 对应的是独立项目 `PPT-Engineering`，这个仓库建议遵循下面的协作策略：

1. 平台级说明写在顶层：整体架构、模块分工、接口协作、环境编排放在当前仓库维护。
2. `PPT-Engineering` 内部说明写在子项目：运行时实现细节、页面系统、模式切换策略、开发规范优先写入子项目自身文档。
3. `PPT-Engineering` 的独立项目能力默认保留：不要为了平台接入删除现有文件管理、编辑器、资源管理等独立项目能力。
4. 平台能力通过新增模式接入：Backend 同步、内部 API、动态构建、自愈重启等能力优先以 `PPT-Engineering` 的 `platform-runtime` 模式补充，不直接污染 `standalone` 流程。
5. 若存在跨仓库协议变更，需同步更新顶层 README、接口文档和部署说明，避免控制面与数据面理解不一致。

推荐的同步流程如下：

1. 在 `PPT-Engineering` 上游仓库完成能力开发与验证。
2. 提交并推送 Runtime 更新。
3. 回到当前仓库更新 `runtime` 子模块指向的新提交。
4. 如有接口、环境变量、启动方式变化，同步更新当前仓库文档。

推荐的 `PPT-Engineering` 演进顺序如下：

1. 抽象 `runtimeMode` 与能力开关层。
2. 保持 `standalone` 模式继续可用。
3. 为 `platform-runtime` 模式新增内部 API、初始化拉取与动态构建能力。
4. 最后再接入 Docker 自愈与完整任务链路。

## 6. 开发约定

### 包管理与环境

- 前端项目统一使用 `pnpm`。
- Python 项目统一使用 `uv` 管理依赖，使用 `venv` 管理虚拟环境。
- 推荐 Node.js 18+。
- 推荐 Python 3.10+。

### 代码与文档约束

- 使用中文进行协作和文档编写。
- 单个文件尽量不超过 1000 行；超过时建议拆分。
- 每个源代码文件开头应包含文件功能描述。
- 为函数补充中文注释，优先解释职责、输入输出和关键约束。

## 7. 当前仓库状态

截至当前版本：

- `runtime/` 已作为独立项目 `PPT-Engineering` 的 Git 子模块接入，并有独立可运行内容。
- `PPT-Engineering` 当前更接近 `standalone` 模式基线，已经具备本地文件管理、可视化编辑和 Vite HMR 能力。
- `PPT-Engineering` 规划中的 `platform-runtime` 模式尚未落地，Backend 同步、内部鉴权 API、动态构建回传、自愈重启能力仍需补齐。
- `backend/` 与 `editor/` 目录已预留，但仍处于待建设状态。
- 顶层仓库当前主要用于沉淀平台架构、集成边界与后续实现规划。

这意味着，现阶段最重要的工作不是重复建设 `PPT-Engineering`，而是在保留 `standalone` 能力的前提下，围绕它补齐平台模式所需能力：

- Runtime 模式切换与能力隔离层
- Backend 与 `PPT-Engineering` 的内部 API 协议
- Editor 与 Backend 的交互模型
- Docker Compose 编排方案
- 构建产物托管与部署闭环

## 8. 后续建议

如果下一步准备开始工程落地，建议优先按下面顺序推进：

1. 定义 Backend 与 Runtime 的内部接口契约。
2. 为 `PPT-Engineering` 引入 `runtimeMode` 和能力开关。
3. 补齐 `docker-compose.yml` 与统一环境变量方案。
4. 初始化 Backend 服务骨架与数据库模型。
5. 初始化 Editor 工作台骨架与预览容器。
6. 建立端到端的“保存 -> 同步 -> HMR”最小闭环。

## 9. 许可证说明

当前仓库 `web-presentation` 顶层内容采用 Apache License 2.0，见 [LICENSE](./LICENSE)。

需要特别注意：

- 顶层 `LICENSE` 仅覆盖当前仓库顶层维护的代码与文档。
- `runtime/` 是独立项目 `PPT-Engineering` 的 Git 子模块，继续遵循它自身仓库内声明的许可证。
- 在当前工作区中，`PPT-Engineering` 的许可证文件位于 [runtime/LICENSE](./runtime/LICENSE)。

如果后续新增其他子模块或引入第三方代码，应继续保持“各自许可证各自生效”的边界，不要默认由顶层许可证统一覆盖。

## 10. 参考文档

- Runtime 项目说明：[runtime/README.md](./runtime/README.md)
- Runtime 协作说明：[runtime/AGENTS.MD](./runtime/AGENTS.MD)
