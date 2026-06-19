<!-- 文件功能：记录 web-presentation 当前已落地能力、仍在建设的范围和后续演进方向。 -->
# 当前状态与路线

## 已落地能力

- `runtime/` 已作为独立项目 `web-runtime-vue` 的 Git 子模块接入，并具备独立运行、测试和 Docker Release 流程。
- `backend/` 已具备 FastAPI、SQLAlchemy 2.0 async、Alembic、多用户登录、工作空间成员隔离、工作空间/项目/页面 CRUD 基线。
- Backend 已内嵌基于 Pydantic AI 的智能体运行入口，注册 `agent-coordinator`、`component-manager` 和 `resource-manager` 三个稳定入口。
- 智能体会话链路采用 session-first：Editor 围绕 `session_id` 工作，Backend 以平台自有 `ai_agent_*` 表维护 run、HITL、事件回放和历史状态。
- 智能体支持工具确认、结构化单选提问、会话恢复、停止/强制结束和图片输入链路。
- 用户级 AI 设置已支持模型配置、槽位绑定、智能体描述、业务补充提示词、工具说明和工具提示词覆盖。
- `backend/app/ai/tool_specs.py` 是智能体工具目录、风险级别、确认要求、上下文要求、调用格式和返回示例的单一事实源。
- `editor/` 已具备 Vue 3、Vue Router、Pinia、工作空间/项目/页面 CRUD、账户设置页和统一 AI 侧边栏。
- 工作空间已提供资源库、组件库、主题库和样式库。
- 项目页面展示配置已统一维护页面宽高、基础字号和默认描边宽度。
- Runtime 预览与构建态通过 Backend 配置接口在线拉取 `app/icons/routes/themes`，临时预览、代码检查、组件预览和截图预览 artifact 使用 Redis 保存。
- 项目级路由由 Editor 通过 UI 编排并以 Backend 结构化数据存储，Runtime 所需路由结构由 Backend 动态组装。
- 根仓已具备平台单镜像 `Dockerfile`、`deploy/` simple/生产可维护/内置依赖 compose 模板和 GitHub Release 到 Docker Hub 的发布 workflow。

## 建设中事项

- Runtime 与 Backend 的协作会继续增强，让预览、诊断、截图和构建状态更稳定地进入项目工作流。
- AI 上下文会继续收敛为更清晰的项目级、工作空间级层次，减少跨项目资产引用和当前页面任务之间的噪声。

## 后续方向

- 完善共享样式库、共享组件库和共享资源库，让团队资产可以跨项目发现、复用、更新和治理。
- 增强多用户协作，围绕成员角色、项目编辑、协作状态和变更确认补齐更明确的工作流。
- 优化预览、截图等高频链路性能，减少创作过程中的等待时间。
- 进一步优化项目上下文，将项目上下文与工作空间上下文做更清晰的软隔离，降低 AI 在当前页面任务、项目资产和工作空间资产之间混淆的概率。
- 扩展构建产物管理、发布版本管理和部署目标。
- 强化 Runtime 与 Backend 的双向协作契约。
- 持续收敛 AI 工具规格、用户配置和前端披露说明，避免工具元数据漂移。
