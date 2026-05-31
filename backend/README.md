<!-- 文件功能：说明页面管理一期后台服务的启动方式、环境变量与常用命令。 -->
# Backend

`backend/` 是页面管理一期后台服务，负责：

- 多用户登录、会话与平台用户管理
- 工作空间 CRUD 与成员隔离
- 项目 CRUD
- 工作空间内页面资源库 CRUD
- 页面资源版本管理（最新基线、向后 diff、重点快照、历史恢复）
- 工作空间组件草稿保存、正式发布版本管理与历史发布预览
- 前端显式命名页面文件并上传到 Runtime
- 基于 Runtime 预览页的页面截图保存

## 1. 环境准备

1. 复制 `.env.example` 为 `.env`
2. 启动 PostgreSQL
3. 配置 Runtime 内网访问地址与共享密钥
4. 使用 `uv` 安装依赖并初始化虚拟环境

数据库连接相关环境变量：

- `DATABASE_URL`：Backend 主数据库连接串
- `DATABASE_CONNECT_TIMEOUT_SECONDS`：数据库连接超时时间（秒），用于启动期和请求期快速暴露连库故障，默认 `10`

推荐直接在仓库根目录启动开发数据库：

```powershell
docker compose -f .\docker-compose.dev.yml up -d
```

平台测试分层、目录约定和 CI 规则见：

- [../docs/testing-strategy.md](../docs/testing-strategy.md)

## 2. 常用命令

安装依赖：

```powershell
uv sync
```

执行数据库迁移：

```powershell
uv run alembic upgrade head
```

初始化默认平台管理员：

```powershell
uv run python -m app.scripts.seed_admin
```

启动开发服务：

```powershell
uv run uvicorn app.main:app --reload
```

安装 Playwright 浏览器：

```powershell
uv run playwright install chromium
```

运行测试：

```powershell
uv run pytest
```

按测试层级筛选：

```powershell
uv run pytest -m unit
uv run pytest -m api
uv run pytest -m integration
uv run pytest -m contract
```

平台 smoke 数据 CLI：

```powershell
uv run python -m app.scripts.reset_test_data
uv run python -m app.scripts.seed_test_data --scenario smoke
```

## 3. 默认平台管理员

- 用户名：`admin`
- 密码：`Admin123456`

如需修改，请直接调整 `.env` 中的 `DEFAULT_ADMIN_USERNAME`、`DEFAULT_ADMIN_PASSWORD` 与 `DEFAULT_ADMIN_DISPLAY_NAME`。平台启动后可通过用户管理接口或 Editor 用户管理页继续创建普通工作空间用户。

## 4. 多用户与工作空间隔离

Backend 直接采用多用户模型，不保留单管理员兼容层：

- 平台用户表为 `users`，会话表为 `user_sessions`，浏览器 Cookie 为 `wp_user_session`
- 用户角色分为 `platform_admin` 与 `workspace_user`
- 平台管理员负责用户管理、全局 AI 默认和全局模型池，不会因为角色自动获得用户工作空间权限
- 用户创建工作空间时会自动写入 `workspace_members.owner`
- 项目、页面、组件、资源、主题、样式、构建和 AI scope 均按工作空间成员关系校验
- 首期不开放公共工作空间；协作通过 `workspace_members` 预留

## 5. AI 模型配置规则

大模型配置分为两类：

- `global`：平台管理员维护的全局模型，普通用户可选择绑定但不可修改
- `personal`：用户本人维护的个人模型，仅本人可见和可编辑

槽位绑定优先级为：用户个人槽位绑定 > 管理员全局默认槽位。Agent 提示词与工具配置继续按“用户覆盖 > 管理员全局默认 > 系统内置默认”的方向演进。

## 6. 业务时区配置

Backend 统一采用以下时间语义：

- 数据库存储统一使用 `UTC`
- 业务编码日期、页面普通版本号、前端展示推荐统一使用业务时区

请通过环境变量配置业务时区：

- `APP_TIMEZONE`：业务时区，例如 `Asia/Shanghai`

说明：

- `page_versions.version_label` 这类展示型版号会按 `APP_TIMEZONE` 生成
- `WS/PRJ/PG` 业务编码中的日期段也会按 `APP_TIMEZONE` 生成
- 若调整了 `APP_TIMEZONE` 并希望旧的普通版本号同步刷新，请重新执行 `uv run alembic upgrade head`

## 7. Runtime 接入配置

当需要使用 Runtime 文件上传接口时，请补充以下环境变量：

- `RUNTIME_BASE_URL`：Runtime 开发服务地址，例如 `http://127.0.0.1:7373`
- `RUNTIME_PUBLIC_BASE_URL`：浏览器访问预览页时应直连的 Runtime 地址；未配置时回退到 `RUNTIME_BASE_URL`
- `RUNTIME_SHARED_SECRET`：Backend 与 Runtime 约定的共享密钥
- `RUNTIME_SERVICE_TOKEN_AUDIENCE`：Backend 为 Runtime 内部 artifact 接口签发短期服务令牌时使用的 audience
- `RUNTIME_REQUEST_TIMEOUT_SECONDS`：Backend 调用 Runtime 内网接口的超时时间（秒）
- `BACKEND_PUBLIC_BASE_URL`：供 Runtime 预览页和未来构建产物回拉项目级 YAML 配置的 Backend 对外地址

当前 Backend 已提供独立 Runtime 文件上传接口：

- 批量上传页面文件：`POST /api/runtime-files/page-files/batch-upload`
- 生成页面预览链接：`POST /api/runtime-files/page-files/preview-link`
- 下发项目级运行时配置：`GET /api/runtime/projects/{project_id}/configs/{app|icons|routes|themes}.config.yaml`

调用方需要显式传入：

- `target_path`：Runtime 内的目标相对目录
- `files[].page_id`：页面 ID，用于读取数据库中的 `page_content`
- `files[].file_name`：前端指定的目标文件名
- `file_path`：已推送到 Runtime 的页面文件路径，用于生成签名预览票据
- `project_id`：当前预览或构建对应的项目 ID，用于拼接项目级配置根地址

Backend 自带项目默认配置模板，路径为 `backend/app/config_templates/*.config.yaml`；Runtime 自身的 `runtime/public/config/*.config.yaml` 仅作为独立运行和本地 fixture 使用。项目创建后，Backend 会自动写入默认主题配置，并为项目自动带上工作空间默认主题。项目页面展示配置由结构化字段维护，包括 `page_width/page_height/base_font_size/icon_default_stroke_width`；Runtime 下发时会映射到 `app.config.yaml`：

```yaml
app:
  page:
    width: 1920
    height: 1080
    baseFontSize: 20px
    iconDefaultStrokeWidth: 2
```

主题配置需要特别注意：

- 工作空间级主题主数据由“主题库”维护，项目与组件预览默认配置优先保存 `theme_key`
- 当存在 `theme_key` 时，`themes.config.yaml` 会在 Runtime 拉取时由 Backend 动态组装
- 当 `theme_key` 为空时，Backend 仍兼容 legacy `theme_config_yaml`
- 主题只负责颜色、字体绑定、Logo 与项目图标；基础字号和默认描边宽度不再写入 `themes.config.yaml`
- 组件预览默认配置与会话覆盖也遵循同样规则，并通过 `preview_options.page` 覆盖页面宽高和页面视觉规格
- 样式离线包当前 schema_version 为 2，导入时不再兼容旧 v1 包

其中项目级 `routes.config.yaml` 采用以下约束：

- 叶子路由必须配置 `page_code`
- 分组路由只允许 `children`，不允许页面标识
- 旧版 `component` 字段不再兼容
- `page_code` 在当前工作空间范围内解析，不依赖全局唯一
- 路由 `meta` 不支持 `icon`，导航菜单不再渲染项目路由图标
- Runtime 预览和发布时，会由 Backend 根据 `page_code` 解析到页面记录，再自动转译为 `@/views/<page.code>.vue`

## 8. 内容助手（Agno）

Backend 现已内嵌基于 Agno 的智能体运行时，但不挂载 AgentOS routes，也不使用 AgentOS run API。Editor 通过 `/api/ai/*` 调用 Backend BFF，Backend 直接构建 Agno `Agent` 或 `Team`，并以 Agno session/run/events 作为会话、运行与 HITL 状态事实源。

当前开放的稳定 Agent 包括：

- `agent-coordinator`：内容助手 Team 入口，保留原会话入口 ID，由内容助手主执行页面/项目能力，直接查询页面可使用的现有组件和资源，并按需调用组件助手、资源助手处理维护类任务
- `component-manager`：管理工作空间组件库，支持 Runtime Kit 公开能力查询、资源读取、组件草稿、源码 edits、元数据维护、发布与删除
- `resource-manager`：管理工作空间资源库，支持资源查询、内容预览/写入、元数据维护、复制与归档

页面编辑与项目管理不再作为独立 Agent 暴露；相关能力由 `agent-coordinator` 内容助手按用户工具配置直接执行，仅在模型不支持图片输入时隐藏截图视觉工具。内容助手可直接读取现有组件和资源用于页面生成/改写；组件/资源维护仍通过 `component-manager`、`resource-manager` 独立入口或内容助手 Team 成员协作完成。

当前链路为：

- 浏览器继续只持有 `wp_user_session` Cookie
- Editor 调用 Backend BFF 路由 `/api/ai/*`
- Editor 以 `session_id` 作为唯一会话主键，主入口为 `POST /api/ai/sessions/{session_id}/runs/stream`
- 前端生成 `run_id`，Backend 调用 Agno `agent/team.arun(..., stream=True, stream_events=True, background=True, run_id=...)`，SSE 直接透传 Agno 原始事件
- HITL 继续执行走 `POST /active-run/continue`，Backend 从 Agno 当前 run 的 active requirements 匹配用户决策，再调用 `agent/team.acontinue_run(...)`
- 客户端断开、切换会话、关闭面板只会关闭当前订阅；重新进入后通过 `runs/{run_id}/events/stream?event_index=N` 从 Agno event buffer 或 Agno DB events 回放
- Backend 以 Agno `AgentSession.runs` 或 `TeamSession.runs` 作为 active-run 主状态源；`pending/running/paused/cancelling` 视为非终态，`completed/cancelled/failed` 视为终态，同一 session 同时只允许一个非终态 run
- Editor 停止运行时调用 `POST /active-run/cancel`；running run 调用 Agno `cancel_run()`，paused run 无后台任务时直接把 Agno DB 中对应 run 标记为 `cancelled`
- Backend 重启后 Agno event buffer 会丢失；paused run 仍可继续，running 且缺少 buffer 的 run 会在懒加载快照时标记为 `cancelled`
- 历史上下文使用 Agno 内置历史注入，按模型 `context_window_tokens`、`max_output_tokens`、`history_token_ratio` 动态计算 `num_history_messages`，不再固定 `num_history_runs=20`
- Agent 工具级鉴权使用短期签名 token，承载 `run_id/session_id/agent_id/user_id/workspace/page/scopes/exp`；工具调用只校验 token、scope 和资源归属，不再查询 Redis run 状态
- 不同 session 可并行执行；当前默认单实例或按 session/run 粘性路由部署，不额外支持跨实例实时续流

当前工具按入口分组装配：

- 所有智能体：内置不可关闭的 `ask_user`，用于一次提出一个或多个结构化单选问题；Editor 在输入区覆盖式展示，支持逐题回答、前后切换、预设选项或自定义回答，不暴露 `get_user_input` 自由字段工具
- `agent-coordinator`：按用户工具配置直接启用内容读取、项目描述/样式配置读取、组件读取、资源读取、页面写入、页面截图与项目写入工具；组件读取仅包含 `list_components`、`get_component_detail`，资源读取包含 `list_resource_assets`、`get_resource_asset_content`、`list_resource_tags`；项目样式配置写入工具 `update_project_style_config` 会通过 Agno 用户确认暂停执行；组件/资源维护能力通过 Team 成员工具执行，成员工具事件会带 `member_agent_id`、`member_agent_name`、`member_run_id` 供 Editor 展示来源
- `component-manager`：`list_components`、`get_component_detail`、`list_component_versions`、`get_component_dependencies`、`list_runtime_kit_capabilities`、`get_runtime_kit_capability`、`list_resource_assets`、`get_resource_asset_content`、`list_resource_tags`、`check_component_code`、`create_component`、`apply_component_edits`、`update_component_metadata`、`publish_component`、`delete_component`
- `resource-manager`：`list_resource_assets`、`get_resource_asset_content`、`list_resource_tags`、`create_resource_asset`、`preview_resource_content_diff`、`apply_resource_content_diff`、`update_resource_asset_metadata`、`copy_resource_asset`、`archive_resource_asset`

其中项目样式配置写入、路由整树覆盖、路由节点移除与组件删除通过 Agno 确认暂停执行；结构化提问同样通过 Agno paused run 恢复；`apply_page_edits` 和 `apply_component_edits` 在写入前强制执行 Runtime validate，校验失败不落库。页面写入调用时必须显式传入目标 `page_id`，并使用 `base_version_no` 做乐观锁；组件写入使用 `base_draft_hash` 与 `base_published_version_no` 锁定当前草稿。

用户级智能体配置由内置目录和用户配置合成：

- 智能体入口保持系统内置，不提供用户开关；可用性仍由模型槽位、图片输入能力、用户工具配置和权限判断
- `ai_agent_user_configs` 保存用户对智能体描述与业务补充提示词的配置；内容助手 Team 成员描述通过对应成员 Agent 的描述配置读取，平台底线提示词不允许编辑
- `ai_agent_tool_user_configs` 保存单工具开关与工具说明/提示词覆盖；系统引导工具不可关闭，确认策略、工具名、参数 schema 和鉴权 scope 不允许被用户修改
- 新 run 会读取最新用户配置；正在运行的 Agno run 不被强制中断

新增环境变量：

- `AI_ENABLED`：是否启用内容助手
- `AI_MODEL_ID`：OpenAI-compatible 模型 ID
- `AI_MODEL_BASE_URL`：可选，自定义 OpenAI-compatible Base URL
- `AI_MODEL_API_KEY`：模型 API Key
- `AI_AGENT_OS_ID`：历史兼容字段，当前 BFF 后台运行链路不调用 AgentOS routes
- `AI_AGENT_TOKEN_TTL_SECONDS`：历史兼容 Agent Token TTL（秒）
- `AI_TOOL_AUTH_WINDOW_SECONDS`：工具 run 级授权滑动窗口（秒），默认 1800
- `AI_TOOL_AUTH_MAX_SECONDS`：工具 run 级授权绝对上限（秒），默认 7200
- `AI_DB_URL`：可选，覆盖 Agno 会话数据库连接
- `AI_DB_SCHEMA` / `AI_SESSION_TABLE` / `AI_APPROVALS_TABLE`：Agno 会话与审批存储配置
- `AI_SESSION_RETENTION_DAYS`：Agno 会话保留天数，默认 `15`；按 `updated_at` 判断，缺失时使用 `created_at`
- `AI_SESSION_CLEANUP_INTERVAL_SECONDS`：Agno 会话历史后台清理间隔，默认 `21600`，设为 `0` 时关闭清理
- `AI_SESSION_CLEANUP_BATCH_SIZE`：单批扫描和删除的 session 数量上限，默认 `500`
- `AI_TEST_MODE`：测试模式；当前支持 `disabled`、`mock`，平台 E2E 推荐使用 `mock`

Agno 会话历史清理只删除超过保留期未更新的整条 session，不做消息级裁剪、事件压缩或摘要迁移。PostgreSQL JSONB/TOAST 已产生的表膨胀不会因为普通删除立即释放物理磁盘；如需回收磁盘空间，应由运维窗口手动执行 `VACUUM FULL`、`pg_repack` 等维护操作，Backend 不会自动执行重型 vacuum。

当前接口：

- `GET /api/ai/agents`
- `GET /api/ai/agent-catalog`
- `GET /api/ai/agent-configs`
- `PATCH /api/ai/agent-configs/{agent_id}`
- `PATCH /api/ai/agent-configs/{agent_id}/tools/{tool_key}`
- `GET /api/ai/sessions`
- `POST /api/ai/sessions`
- `PATCH /api/ai/sessions/{session_id}`
- `GET /api/ai/sessions/{session_id}/messages`
- `POST /api/ai/sessions/{session_id}/runs/stream`
- `GET /api/ai/sessions/{session_id}/runs/{run_id}/events/stream`
- `GET /api/ai/sessions/{session_id}/active-run`
- `POST /api/ai/sessions/{session_id}/active-run/continue`
- `POST /api/ai/sessions/{session_id}/active-run/cancel`：幂等取消当前非终态 run；请求体支持 `force=true` 在停止超时后强制释放当前 session 占用

## 9. 页面截图能力

Backend 现已支持基于 Runtime 预览页生成页面截图，并将结果保存为单页面单图覆盖文件。

相关环境变量：

- `PAGE_SCREENSHOT_DEFAULT_VIEWPORT_WIDTH`：默认截图宽度，默认 `1920`
- `PAGE_SCREENSHOT_DEFAULT_VIEWPORT_HEIGHT`：默认截图高度，默认 `1080`
- `PAGE_SCREENSHOT_MAX_VIEWPORT_WIDTH`：允许的最大截图宽度，默认 `4096`
- `PAGE_SCREENSHOT_MAX_VIEWPORT_HEIGHT`：允许的最大截图高度，默认 `4096`
- `PAGE_SCREENSHOT_TIMEOUT_SECONDS`：截图整体超时时间（秒），默认 `45`
- `PAGE_SCREENSHOT_VISUAL_READY_TIMEOUT_SECONDS`：等待图片、背景图与字体等视觉资源就绪的超时时间（秒），默认 `25`
- `ASSET_STORAGE_DRIVER`：统一对象存储驱动，支持 `local` 与 `s3`
- `S3_BUCKET`：S3/R2 私有资产 bucket，用于图片、视频、文档类工作空间资源与平台内部对象
- `S3_PUBLIC_BUCKET`：可选的公开字体 bucket；配置后字体文件（`.woff2`、`.woff`、`.ttf`、`.otf`）会写入该 bucket
- `S3_PUBLIC_BASE_URL`：可选的公开字体访问根地址；配置后 `/public/assets/{workspace_id}/{file_hash}` 会把字体重定向到稳定公开 URL
- `PAGE_SCREENSHOT_LOCAL_ROOT`：本地对象存储根目录，默认 `backend/data`
- `PAGE_SCREENSHOT_BROWSER_EXECUTABLE_PATH`：可选，显式指定 Chromium 可执行文件路径
- `OBJECT_CACHE_IDLE_DAYS`：对象存储派生缓存闲置清理天数，默认 `30`
- `OBJECT_CACHE_MAX_BYTES`：对象存储派生缓存容量上限，默认 `10737418240`
- `OBJECT_CACHE_SWEEP_INTERVAL_SECONDS`：对象存储派生缓存机会式扫描间隔，默认 `21600`

当前接口：

- 保存页面截图：`POST /api/pages/{page_id}/screenshot`

说明：

- 当前仅支持 `vue` 页面截图
- 请求体可选传入 `viewport_width`、`viewport_height`
- 返回的 `PageItem` 会包含 `screenshot_url` 与 `screenshot_updated_at`
- 页面截图预览会通过 `/public/cached-assets/{workspace_id}/{file_hash}` 读取工作空间资源；该入口只使用派生缓存，不改变资源管理策略
- 截图通过 `/public/page-screenshots/{page_id}` 稳定公开入口访问；S3 私有桶由 Backend 代理读取后返回图片内容

## 10. 页面版本能力

页面资源以 `pages.page_content` 保存当前最新源码，同时通过 `page_versions` 维护版本链：

- 当前最新版本始终保存为完整快照
- 普通历史版本默认保存为“从新到旧”的向后 diff
- 重点版本可升级为完整快照，便于长期留存和快速恢复
- 普通保存版本展示号使用 `年月日-时分秒`，重点快照展示号使用 `V1`、`V2`，若在两个主快照之间补打快照，则使用 `1.1`、`1.11` 这类子版本号
- 普通保存版本展示号中的时间基于 `APP_TIMEZONE`

当前可用接口包括：

- 查询版本历史：`GET /api/pages/{page_id}/versions`
- 查询指定版本内容：`GET /api/pages/{page_id}/versions/{version_no}`
- 创建重点快照：`POST /api/pages/{page_id}/versions/{version_no}/snapshot`
- 恢复历史版本：`POST /api/pages/{page_id}/versions/{version_no}/restore`

说明：

- 页面首次创建时会自动生成 `V1` 初始版本
- 当 `page_content` 或 `file_type` 发生变化时，会自动生成新的最新版本
- 恢复历史版本不会覆盖旧记录，而是基于目标版本内容创建一个新的最新版本

## 11. 组件草稿与发布版本能力

工作空间组件采用“单一草稿 + 正式发布版本”模型：

- `workspace_components.content / preview_schema / file_type` 保存当前可编辑草稿
- `workspace_components.import_name` 保存源码默认导入引用名，必须是 PascalCase 英文标识符，并在同一工作空间启用组件内唯一
- `workspace_component_versions` 只保存正式发布后的不可变版本
- `workspace_components.current_version_no` 表示最新已发布版本号；新建未发布组件为 `0`
- 页面和其他组件只能引用已发布版本：`import SalesMetricCard from '@workspace-components/<component_code>/v/<version_no>'`，其中路径仍使用稳定组件编码和版本号
- 草稿可以频繁保存和预览，不会自动生成可引用版本

当前可用接口包括：

- 创建组件草稿：`POST /api/components`
- 保存组件草稿：`PATCH /api/components/{component_id}`
- 发布当前草稿：`POST /api/components/{component_id}/publish`
- 查询发布历史：`GET /api/components/{component_id}/versions`
- 查询发布版本内容：`GET /api/components/{component_id}/versions/{version_no}`
- 恢复发布版本到草稿：`POST /api/components/{component_id}/versions/{version_no}/restore-to-draft`
- 预览发布版本：`POST /api/components/{component_id}/versions/{version_no}/preview-artifact`

说明：

- `publish` 入参支持 `release_name` 与 `change_note`
- 恢复发布版本到草稿不会改变外部引用；只有再次发布才会生成新的版本号
- 引用未发布组件或不存在的组件版本时，保存页面/组件会返回明确错误
