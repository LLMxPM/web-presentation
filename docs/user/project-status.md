<!-- 文件功能：记录 web-presentation 当前已落地能力、仍在建设的范围和后续演进方向。 -->
# 当前状态与路线

## 已落地能力

- `runtime/` 已作为独立项目 `web-runtime-vue` 的 Git 子模块接入，并具备独立运行、测试和 Docker Release 流程。
- `backend/` 已具备 FastAPI、SQLAlchemy 2.0 async、Alembic、多用户登录、工作空间成员隔离、工作空间/项目/页面 CRUD 基线。
- Backend 已内嵌基于 Agno 的智能体运行时，注册 `agent-coordinator`、`component-manager` 和 `resource-manager` 三个稳定入口。
- 智能体会话链路采用 session-first：Editor 围绕 `session_id` 工作，Backend 以 Agno session/run/events 维护 run、HITL、事件回放和历史状态。
- 智能体支持工具确认、结构化单选提问、会话恢复、停止/强制结束和图片输入链路。
- 用户级 AI 设置已支持模型配置、槽位绑定、智能体描述、业务补充提示词、工具说明和工具提示词覆盖。
- `backend/app/ai/tool_specs.py` 是智能体工具目录、风险级别、确认要求、上下文要求、调用格式和返回示例的单一事实源。
- `editor/` 已具备 Vue 3、Vue Router、Pinia、工作空间/项目/页面 CRUD、账户设置页和统一 AI 侧边栏。
- 工作空间已提供资源库、组件库、主题库和样式库。
- 项目页面展示配置已统一维护页面宽高、基础字号和默认描边宽度。
- Runtime 预览与构建态通过 Backend 配置接口在线拉取 `app/icons/routes/themes`，临时预览、代码检查、组件预览和截图预览 artifact 使用 Redis 保存。
- 项目级路由由 Editor 通过 UI 编排并以 Backend 结构化数据存储，Runtime 所需路由结构由 Backend 动态组装。
- 根仓已具备平台单镜像 `Dockerfile`、`deploy/` simple/生产可维护/内置依赖 compose 模板和 GitHub Release 到 Docker Hub 的发布 workflow。

## 当前限制

- 跨项目资产治理、Dashboard、项目/页面使用关系运营视图仍在建设中。
- Runtime 反向回传 Backend 的目标态能力尚未完全落地。
- 长链路 AI、截图、PDF、打印等场景仍适合通过夜间或手动扩展回归覆盖。
- Runtime 子模块与根仓平台 Release 存在顺序要求：必须先发布 Runtime `sha-<12位提交>` 镜像，再更新根仓子模块指针并发布平台镜像。

## 后续方向

- 完善跨项目资产治理和使用关系运营视图。
- 完善 Dashboard 与跨项目运营视图。
- 扩展构建产物管理、发布版本管理和部署目标。
- 强化 Runtime 与 Backend 的双向协作契约。
- 持续收敛 AI 工具规格、用户配置和前端披露说明，避免工具元数据漂移。
