<!-- 文件功能：仓库级协作说明文档，约束人在环与智能代理在本仓库中的修改边界、开发规范、文档维护策略与子模块协同方式。 -->
# AGENTS.md

本文档用于约束在 `web-presentation` 仓库内工作的开发者与智能代理行为，目标是保证平台规划、项目实现与 `runtime` 子项目协作保持一致。

## 1. 仓库定位

这是一个平台集成仓库，不只是单纯的前端项目。

仓库目标包括：

- 维护平台级架构设计与模块边界
- 管理 `backend`、`editor` 与 `runtime` 的协作方式
- 沉淀控制面与数据面的接口契约
- 承载 Docker 编排、环境变量规范与部署集成说明

当前需要特别注意的是：`runtime/` 是独立项目 `web-runtime-vue` 的子模块接入目录，而不是本仓库内部普通子目录；它需要同时兼顾独立项目形态和平台运行时形态。

## 2. 目录职责

### 顶层目录

- `README.md`：面向项目成员，说明平台目标、架构、流程、模块边界与协作方式。
- `AGENTS.md`：面向开发者与智能代理，说明本仓库的修改约束与工作规则。

### backend/

用于承载 Backend 控制面服务。未来实现应聚焦：

- 文件与配置持久化
- 历史版本与快照管理
- Runtime 调度
- 构建任务状态管理
- 产物接收与托管

### backend/app/ai

用于承载基于Agno的智能体相关功能，包括但不限于：
- 智能体注册与管理
- 智能体调用
- 智能体执行结果处理
- 智能体工具规格、工具组、调用契约与返回示例

`backend/app/ai/tool_specs.py` 是智能体工具目录、工具组、风险级别、确认要求、上下文要求、调用格式与返回示例的单一事实源。`agent_catalog.py`、`tools/disclosure.py`、组件管理工具注册、`/ai/agent-catalog` 与 `/ai/agent-configs` 返回给 Editor 的工具配置都应从该规格派生，不应重复手写工具清单或分组描述。

### editor/

用于承载 Editor 工作台。未来实现应聚焦：

- 代码编辑
- 文件树与组件选件
- Iframe 预览
- 构建操作入口
- 智能体调用入口
- Runtime 重启态感知

账户 AI 设置页应展示面向 Agent 的完整工具说明，包括当前生效说明、系统默认说明、参数 JSON Schema、调用示例、返回示例、上下文要求与运行时披露组。工具调用契约和返回示例是系统只读信息，用户只允许编辑智能体描述、业务补充提示词、内容助手 Team 成员描述、工具说明和工具提示词。

### runtime/

这是独立项目 `web-runtime-vue` 在当前仓库中的接入目录，负责：：

- 运行时预览
- 基于 Vite 的本地 HMR 与构建
- 维护 `src/runtime-kit/manifest/runtime-kit.manifest.json`，作为 Backend 校验页面/组件可导入 Runtime 基础能力的公开清单；清单项必须使用 `<ExportName>.v<整数版本>` 命名，并指向带 `.vN` 的公开 import path。

Runtime shell 内部组件、component-preview 宿主页及其辅助类型/组合式能力、PDF 导出、侧栏/缩略图、Toast 与 ErrorBoundary 不应通过 `@runtime-kit` 暴露给页面源码、工作空间组件源码或智能体能力目录。
页面源码、工作空间组件源码与 previewSchema 不允许引用未带 `.vN` 的 `@runtime-kit` 公开路径；需要不兼容演进时新增 v2/v3 文件，不修改仍被依赖的旧版本文件。


### 命名约定

- `web-runtime-vue`：指独立项目名称。
- `runtime/`：指 `web-runtime-vue` 在当前仓库中的目录路径。
- `Runtime`：指平台架构中的运行时角色。



## 3. 文档维护规则

### 什么时候更新顶层 README

出现以下情况时，应同步更新顶层 `README.md`：

- 平台愿景、模块职责或架构关系发生变化
- Backend、Editor、Runtime 的边界重新划分
- 内部关键流程发生变更
- 子模块协作方式、部署方式或开发入口改变

### 什么时候更新顶层 AGENTS

出现以下情况时，应同步更新顶层 `AGENTS.md`：

- 团队协作规范发生变化
- 新增统一编码约束或文档约束
- 子模块修改策略变化
- Monorepo 结构新增或调整

### 什么时候更新 Runtime 文档

出现以下情况时，应优先更新 `web-runtime-vue` 自身文档：

- `web-runtime-vue` 新增开发命令、目录结构或基础能力
- `web-runtime-vue` 插件系统、构建机制、页面体系发生变化
- `web-runtime-vue` 内部编码规范、页面开发方式发生变化


## 4. 编码注意事项

- 新增 Python 代码时，优先采用清晰的模块拆分，不要把路由、模型、服务全部写入单文件。
- 新增前端代码时，优先拆分视图、组件、状态逻辑和 API 请求层。
- 新增、删除或调整 Agno 工具时，必须先更新 `backend/app/ai/tool_specs.py`；随后通过规格派生目录、披露组和前端说明，不要在 `agent_catalog.py`、`tools/disclosure.py` 或 Editor 里复制第二份工具元数据。
- 调整工具参数、确认要求、风险级别、上下文要求或返回结构时，应同步更新工具规格中的调用说明和返回示例，并补充或更新防漂移测试，确保目录工具 key、实际 Agno Function、披露工具组与前端 `agent_guide` 一致。
- 如果接口契约尚未稳定，先在文档中声明请求路径、入参、出参和错误语义，再开始跨模块联调。
- 如果需要为平台新增共享约束，优先写入顶层文档，而不是只留在会话记录里。
- 涉及到Agno开发，特别是引入新特性时，需要查阅https://docs.agno.com/introduction文档后再确定开发方式
