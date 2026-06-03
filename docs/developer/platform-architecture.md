<!-- 文件功能：说明 web-presentation 的平台目标、控制面/数据面架构、模块职责、目标业务流程和 Runtime 子模块协作方式。 -->
# 平台架构说明

## 平台目标

`web-presentation` 面向 Vue 组件开发与可视化编排场景，目标是提供一套可私有化部署的 Web IDE + Runtime + Backend 协作体系。

平台围绕四个方向设计：

1. 极速预览体验：通过 Runtime 驱动 Vite 预览链路，让 iframe 预览快速响应页面变化。
2. 数据持久化安全：代码、配置、版本和产物事实写入 Backend，运行容器只保留可丢弃运行态。
3. 动态编排与打包：支持用户选择多个页面或组件，动态生成入口并输出标准化构建产物。
4. 环境高可用与自愈：依赖变更或运行态异常可通过容器重启、健康检查和恢复流程收敛。

## 总体架构

系统采用“控制面 + 数据面”解耦模式：

- **Backend**：控制中枢，负责数据持久化、任务调度、权限校验、预览 artifact、构建产物托管和 AI Agent 运行态。
- **Editor**：用户操作界面，负责项目配置、页面编辑、组件管理、资源管理、构建触发和预览呈现。
- **Runtime**：执行引擎，负责加载 Backend 下发的预览上下文、远程模块、配置包，并执行预览、诊断和构建。
- **Infra**：通过 Docker / Docker Compose / GitHub Actions 负责服务编排、镜像发布、网络隔离和容器自愈。

## 模块职责

### Backend

- 多用户登录、会话和平台用户管理。
- 工作空间成员隔离下的工作空间、项目、页面 CRUD。
- 工作空间级资源库、组件库、主题库和样式库主数据管理。
- 页面源码、工作空间组件源码与 previewSchema 的导入边界校验。
- 基于 `backend/app/ai/tool_specs.py` 维护 AI 工具规格单一事实源。
- 预览 artifact、构建 snapshot、构建任务状态和产物托管。

### Editor

- 用户登录页、账户设置页与平台管理员用户管理页。
- 工作空间、项目、页面、组件、资源、主题和样式管理界面。
- Monaco 代码编辑、iframe 预览、构建触发和构建历史查看。
- AI Agent 入口、工具说明展示、会话恢复和 HITL 确认交互。

### Runtime

`runtime/` 是独立项目 `web-runtime-vue` 在当前仓库中的接入目录。它不是根仓普通子目录，而是 Git 子模块。

Runtime 维护页面可引用基础能力的公开契约：`runtime/src/runtime-kit/manifest/runtime-kit.manifest.json` 是 Backend 校验 `page_content`、工作空间组件源码与组件预览 schema 的单一事实源。公开能力采用文件名版本化，`name` 形如 `Icon.v1`，`import_path` 必须指向带 `.vN` 的文件。

页面和工作空间组件只能通过清单中的版本化 `@runtime-kit/...` 路径引用公开能力；未带 `.vN` 的旧路径会被 Backend 拒绝。Runtime shell、component-preview 宿主页、PDF 导出、布局侧栏、Toast、ErrorBoundary 等壳层能力不进入该清单，也不进入智能体能力目录。

## 目标业务流程

### 代码保存与预览

1. 用户在 Editor 中编辑页面或组件。
2. Editor 调用 Backend 保存接口。
3. Backend 写入数据库，并在需要预览时创建 preview artifact。
4. Backend 为 Runtime 预览签发短期上下文令牌。
5. Runtime 通过 `/__preview` 加载上下文、配置包、远程模块和静态资源。
6. Editor iframe 展示 Runtime 渲染结果。

### 依赖变更与环境恢复

1. 用户修改关键依赖或运行配置。
2. Backend 记录变更并触发 Runtime 恢复或重启策略。
3. Docker 根据健康检查和重启策略拉起新容器。
4. Editor 通过健康状态感知恢复进度。

### 动态构建与产物回传

1. 用户在 Editor 中发起项目构建。
2. Backend 创建构建任务和 build snapshot。
3. Runtime 拉取 snapshot，生成临时入口并执行 Vite 构建。
4. Runtime 将构建产物压缩为 zip 并上传回 Backend。
5. Backend 保存产物并返回稳定下载或静态访问地址。

## Runtime 子模块协作

命名约定：

- `web-runtime-vue`：独立 Runtime 项目本身。
- `runtime/`：`web-runtime-vue` 在当前仓库中的子模块路径。
- `Runtime`：平台架构中的运行时角色。

推荐同步流程：

1. 在 `web-runtime-vue` 上游仓库完成能力开发、测试和镜像发布。
2. 确认子仓库 Docker Release 已推送 `web-runtime-vue:sha-<12位提交>`。
3. 回到当前仓库更新 `runtime` 子模块指针。
4. 如有接口、环境变量、启动方式或 manifest 变化，同步更新根仓文档和测试。
