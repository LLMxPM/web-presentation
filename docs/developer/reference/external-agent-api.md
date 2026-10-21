# External API v1 契约与外部 Agent 接入边界

## 1. 文档归属

本文是 `web-presentation` 主仓库维护的 External API v1 契约文档，服务于同级独立仓库 [web-presentation-cli](https://github.com/LLMxPM/web-presentation-cli)（CLI、同步客户端与 Skill）及 [web-presentation-mcp](https://github.com/LLMxPM/web-presentation-mcp)（MCP Server，待完成状态）。

本文只维护平台侧事实：

- External API v1 的公开边界、路径和版本策略；
- PAT、Scope、工作空间隔离和错误语义；
- 页面、组件、资源、主题、样式和 Mutation Job 的后端契约；
- `/standards/*`、`/capabilities` 和 OpenAPI 等自省接口；
- 主仓库契约测试、兼容性和变更流程。

本文不维护以下内容：

- `wp` CLI 的 Click 命令、参数、终端输出和本地 Profile；
- MCP Tool、Resource、Prompt、传输和协议输出；
- Agent Skill 的工作流提示词；
- 外部客户端仓的 Python 模块结构、发布方式和仓内测试。

对应实现文档：

- CLI 实施矩阵：[web-presentation-cli/docs/cli-capability-completion.md](https://github.com/LLMxPM/web-presentation-cli/blob/main/docs/cli-capability-completion.md)
- MCP 实施规划：[web-presentation-mcp/docs/mcp-implementation-plan.md](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/mcp-implementation-plan.md)
- Skill 知识库：[web-presentation-cli/skills/web-presentation/SKILL.md](https://github.com/LLMxPM/web-presentation-cli/blob/main/skills/web-presentation/SKILL.md)

## 2. 唯一事实源

External API 契约的优先级如下：

1. Backend 实际路由、Pydantic 请求/响应模型和鉴权依赖；
2. `backend/app/core/external_operations.py` 中的 operation 注册表；
3. `tests/contracts/` 中的跨模块契约测试；
4. 本文的语义说明和变更记录。

当本文与代码或契约测试冲突时，先修正主仓契约，再通知客户端仓更新适配；不得由 CLI 或 MCP 猜测并绕过主仓事实。

主仓实现入口：

```text
backend/app/api/routes/external/
backend/app/core/external_operations.py
backend/app/schemas/external_api.py
tests/contracts/
```

## 3. 公共边界

### 3.1 HTTP 前缀

所有外部接入统一使用：

```text
/api/v1
```

禁止重新引入 `/api/external/v1`。Endpoint 配置值只保存 Backend 根地址，公共前缀由客户端拼接。

### 3.2 认证和工作空间

MVP 使用 PAT Bearer：

```http
Authorization: Bearer wp_pat_...
X-Workspace-ID: <workspace_id>
```

工作空间 Header 是资源访问上下文，不是权限替代品。Backend 必须同时校验：

- PAT 用户身份和有效期；
- PAT 所有者的工作空间授权；
- 目标对象的工作空间归属；
- 当前 operation 所需 Scope。

无权对象统一按平台错误契约隐藏其存在性，外部接入不得通过错误差异探测其他工作空间。

### 3.3 Scope

外部接入直接复用以下 Scope，不新增 CLI 或 MCP 私有权限名：

| Scope | 责任范围 |
|---|---|
| `workspace:read` | 工作空间详情和能力矩阵 |
| `project:read` / `project:write` | 项目读取、创建、修改和归档 |
| `page:read` / `page:write` | 页面读取、创建、编辑和归档 |
| `component:read` / `component:write` | 组件读取、创建、编辑、发布和归档 |
| `asset:read` / `asset:write` | 资源读取、上传、内容/元数据更新和归档 |
| `design-system:read` / `design-system:write` | 主题、样式读取和维护 |
| `preview:run` | 页面截图和预览相关能力 |

具体 operation 使用的 Scope 以 `external_operations.py` 和 `/capabilities` 返回为准。

## 4. 自省接口

### 4.1 身份和能力

```text
GET /api/v1/auth/whoami
GET /api/v1/workspaces
GET /api/v1/workspaces/{workspace_id}
GET /api/v1/workspaces/{workspace_id}/capabilities
```

`capabilities` 返回当前 Token 在指定空间可用的 Scope 和 operation。CLI 可以用它决定命令提示，MCP 可以用它决定工具是否披露；两者都不能把客户端判断当作最终授权。

响应中的可选 `slideshow` 字段声明服务端当前实际支持的放映范围。当前结构版本为 schema 2，`advance_modes` 仍为 `manual`/`timer`、`single_window_auto_play` 为 true，`presenter_auto_play` 与 `capture_auto_play` 保持 false；schema 2 同时披露 `media_timeout_ms` 范围，但 `media_end` 在 M2 出口前不可写、不可执行。字段缺失或为 null 表示未声明该功能，客户端不能仅凭配置字段可写就推断可执行。

`slideshow.audio` 声明音频能力（`schema_version=1`）：`audio_assets` 表示可上传和引用音频资源；`page_narration` 与 `audio_cues` 在对应阶段出口验收前保持 false。客户端只能在 `audio_cues=true` 时展示项目 cue 配置；后端写入校验独立于客户端开关。

响应中的可选 `fonts` 声明字体预设能力：`presets.sans` 为 `["platform-sans", "system-ui"]`，`presets.mono` 为 `["platform-mono", "monospace"]`。来源统一以 Backend `app.core.platform_fonts` 为准，CLI 动态发现预设，不维护第二套手写枚举。

### 4.2 规范和 OpenAPI

```text
GET /api/v1/standards/page
GET /api/v1/standards/component
GET /openapi.json
```

页面和组件规范由 Backend 发布；CLI 使用公开 OpenAPI 获取当前服务端的路径、参数和请求 Schema。agent-kit 不复制 Backend DTO 或维护第二份静态 Schema。

## 5. 资源和任务契约

### 5.1 资源接口

主仓维护下列资源的路由、DTO、Scope 和错误语义：

```text
/api/v1/workspaces
/api/v1/projects
/api/v1/projects/{project_id}/pages
/api/v1/pages
/api/v1/components
/api/v1/assets
/api/v1/themes
/api/v1/styles
```

资源具体视图包括详情、源码/草稿、历史版本、资源内容、配置和路由树；是否公开某个视图以实际路由和 operation 注册表为准。

首版 CLI 使用的结构化资源接口包括：

```text
GET/PUT  /api/v1/projects/{project_id}/configuration
POST     /api/v1/projects/{project_id}/audio-cues/clear
GET/PUT  /api/v1/projects/{project_id}/route-tree
POST     /api/v1/projects/{project_id}/apply-style
PUT      /api/v1/projects/{project_id}/build-assets
POST     /api/v1/pages
POST     /api/v1/pages/{page_id}/copy
POST     /api/v1/pages/{page_id}/edits
GET      /api/v1/pages/{page_id}/dependencies
GET      /api/v1/components/{component_id}/dependencies
POST     /api/v1/components/{component_id}/edits
POST     /api/v1/assets/content
GET/PUT  /api/v1/assets/{asset_id}/content
POST     /api/v1/assets/{asset_id}/content/preview
POST     /api/v1/assets/{asset_id}/copy
POST     /api/v1/assets/{asset_id}/replace
GET      /api/v1/assets/tags
GET      /api/v1/runtime-kit
GET      /api/v1/runtime-kit/{item}
GET      /api/v1/fonts
GET      /api/v1/fonts/{font_id}
POST     /api/v1/fonts
PATCH    /api/v1/fonts/{font_id}
GET      /api/v1/font-families
GET      /api/v1/font-families/{family_id}
PATCH    /api/v1/font-families/{family_id}
POST     /api/v1/validate/entity
```

`validate/entity` 的 `entity_type` 为 `page | component`，`mode` 为 `current | content | edits`。项目配置、路由树、主题、样式和资源内容写入均由 Backend Schema 最终校验。

样式创建 `POST /api/v1/styles` 同时接受规范的 `configuration.presentation` 嵌套配置和顶层完整展示字段；OpenAPI 请求 Schema 与该接口保持一致。

#### 资源文件替换

`POST /api/v1/assets/{asset_id}/replace`（operation `asset.file.replace`，scope `asset:write`）以 multipart 上传新二进制文件并按 ID 替换，不改动 asset_type、id 与 name：

- 必须同时携带 `Idempotency-Key` 与 `expected_file_hash`；缺基线按请求校验返回 422。
- `expected_file_hash` 是提交前的版本基线，取资源响应中的 `file_hash`；基线不匹配返回 409 `ASSET_VERSION_CONFLICT`，客户端必须重新读取资源后再决定，不得用旧视图静默覆盖。
- 三维资源（`asset_type=model3d`）必须通过本接口替换；同名覆盖上传会被拒绝，避免按文件名匹配误选其他资源。
- 同幂等键同输入重放首次结果且不生成第二份历史；不同输入复用键返回 409。
- 成功返回 200 `AssetResponse`，`file_hash` 为新文件哈希；历史副本按平台归档规则创建。

#### 音频资源与项目 cue

音频复用统一资源接口，不需要专用上传路径：

- `POST /api/v1/assets` 使用 `asset_type=audio` 上传 `.mp3`、`.m4a`、`.aac`、`.ogg` 或 `.wav`；扩展名与 MIME 的对应关系由 Backend 严格校验。
- `GET /api/v1/assets?asset_type=audio` 只返回音频资源；`GET /api/v1/assets/{asset_id}/file` 读取当前版本二进制。
- 音频替换同样使用 `POST /api/v1/assets/{asset_id}/replace`，必须携带 `expected_file_hash` 与 `Idempotency-Key`。
- `GET/PUT /api/v1/projects/{project_id}/configuration` 的 `audio_settings` 读写项目音量与 cue 绑定；`PUT` 省略 `audio_settings` 保留现有值，完整对象替换，显式 `null` 返回 422，`cue_bindings: []` 清空绑定。
- `POST /api/v1/projects/{project_id}/audio-cues/clear`（operation `project.audio_cues.clear`，scope `project:write`）是原子清空入口：必须携带 `Idempotency-Key`，成功返回 200 `ProjectItem`，`audio_settings.cue_bindings` 为空且三段音量保持当前值。它只删除绑定，不读出并重写音量；能力关闭时仍允许清空历史绑定，但不允许新增或恢复绑定。
- `audio_cues=false` 时，项目创建、项目更新、configuration 更新和模板导入携带非空 `cue_bindings` 返回 422 `AUDIO_CAPABILITY_UNAVAILABLE`；空 `cue_bindings` 与音量更新继续允许。`page_narration=false` 时，页面/组件保存拒绝 `purpose="narration"`，`audio_cues=false` 时拒绝 `useAudioCue`，`validate` 返回相同业务码。
- 读取响应中的 `cue_bindings` 同时给出 `asset_id`、`asset_name`、`asset_type`、`asset_status` 与 `gain_percent`；写入只接受 `asset_id`、`key` 和 `gain_percent`，资源必须属于当前工作空间且为 active 的 audio 类型。
- `ProjectItem` 的 `audio_settings` 使用 ID 形式返回绑定；需要逻辑名时读取项目 configuration 或资源列表。

#### 字体与字体族管理（WP01 冻结）

字体管理遵循“上传文件（asset）→ 注册 face（font）→ 聚合归属（family）”的分阶段模型：

- `asset_id` 是基础文件资源 ID（`asset_type=font`，格式限 `.woff2`、`.woff`、`.ttf`、`.otf`）。通过 `POST /api/v1/assets` 上传文件获得，上传不等于注册。
- `font_id` 是单个 `@font-face` 注册项 ID，关联物理 `asset_id` 与字体族名、`font_format`、`font_weight`、`font_style`、`font_display`。同一资源在同一工作空间内只能注册一次。
- `family_id` 是字体族 ID，用于聚合多个字重/样式的 face，是主题字体槽绑定的唯一合法自定义族 ID（不能以 `asset_id` 或 `font_id` 代替）。
- 接口与操作：
  - `GET /api/v1/fonts`（operation `font.list`，scope `asset:read`）：分页查询已注册 face 列表。
  - `GET /api/v1/fonts/{font_id}`（operation `font.get`，scope `asset:read`）：查询单项 face 详情。
  - `POST /api/v1/fonts`（operation `font.register`，scope `asset:write`）：注册已有字体资源为 face。必须携带 `Idempotency-Key`。接受 `asset_id`、`family_name`，以及可选 `font_format`、`font_weight`（默认 400，支持数值或可变字重范围如 `"100 900"`）、`font_style`（默认 normal）、`font_display`（默认 swap）。禁止未知字段；不开放 `status` 参数（默认 active）。同资源重复注册返回 409 `FONT_CONFIG_ALREADY_EXISTS`，同族同字重与样式返回 409 `FONT_CONFIG_DUPLICATE_FACE`，非 font 返回 400 `FONT_ASSET_REQUIRED`，归档/历史资源返回 400 `FONT_ASSET_INVALID`。
  - `PATCH /api/v1/fonts/{font_id}`（operation `font.update`，scope `asset:write`）：更新 face 配置或通过修改 `family_name` 移动所属族。必须携带 `Idempotency-Key`。禁止修改 `asset_id` 与 `status`。可写字段允许省略但拒绝显式 null（422）；原族未被主题引用且无剩余 face 时自动清理。不能移走仍被主题绑定字体族的最后一个可用 active face，返回 409 `FONT_CONFIG_IN_USE`；归档或资源失效的兄弟 face 不计作可用替代。
  - `GET /api/v1/font-families`（operation `font_family.list`，scope `asset:read`）：分页查询字体族及其内嵌 faces 摘要。
  - `GET /api/v1/font-families/{family_id}`（operation `font_family.get`，scope `asset:read`）：查询单个字体族详情及全部 faces。
  - `PATCH /api/v1/font-families/{family_id}`（operation `font_family.rename`，scope `asset:write`）：重命名字体族。必须携带 `Idempotency-Key`。族名在当前空间内唯一，重名返回 409 `FONT_FAMILY_DUPLICATE_NAME`；同事务级联更新引用该族的主题的对应字体标签。
- 本期范围不包含：字体文件转码/子集化、在线下载、自动元数据推断、注销/停用/硬删除及内部 AI 工具扩权。

#### 主题图片与字体配置（WP01 冻结）

主题通过工作空间共享，支持图片（Logo、反色 Logo、项目图标）与三槽字体（标题、正文、代码）配置：

- 接口与操作：
  - `POST /api/v1/themes`（operation `theme.create`，scope `design-system:write`）：创建主题，必须携带 `Idempotency-Key`。支持一次性写入 `logo_asset_id`、`invert_logo_asset_id`、`project_icon_asset_id`，以及三槽字体配置。palette 省略时使用默认色板；主题 `key` 创建后不可变。
  - `PATCH /api/v1/themes/{theme_id}`（operation `theme.update`，scope `design-system:write`）：部分更新主题配置，必须携带 `Idempotency-Key`。禁止修改 `key`。
- 图片槽位语义（`logo_asset_id`、`invert_logo_asset_id`、`project_icon_asset_id`）：
  - **字段省略**：保持当前绑定与持久化路径不变。
  - **显式 `null`**：清空该图片槽位。同步清理持久化 `logo_path`、`invert_logo_path` 或 `project_icon_name` 为 null，禁止 Runtime 回退历史旧名称。
  - **更新绑定**：传入真实资源 ID。资源必须属于当前空间、active 状态、非历史副本。Logo 允许 `image`/`icon`；项目图标只允许 `icon`，类型/状态不符返回 400 `WORKSPACE_THEME_ASSET_INVALID`。
- 三槽字体配置真值表（以 `heading_font_family_id` 和 `heading_font_preset` 为例，正文/代码同理）：
  - **双省略**：保持原槽位绑定不变。
  - **双显式 `null`**：恢复系统默认预设（标题/正文恢复 `platform-sans`，代码恢复 `platform-mono`）。
  - **仅传非空 `family_id`**：切换为自定义字体族，该槽 preset 自动置为 None。被引用的字体族不存在时返回 400 `WORKSPACE_THEME_FONT_NOT_FOUND`，无可用 active face 时返回 400 `WORKSPACE_THEME_FONT_INVALID`。
  - **仅传非空 `preset`**：切换为内置预设，该槽 family_id 自动置为 None。preset 必须属于 `platform_fonts.py` 规定集合（标题/正文限 `platform-sans`、`system-ui`；代码限 `platform-mono`、`monospace`），否则返回 422 `UNSUPPORTED_FONT_PRESET`。
  - **单传 `null`**（仅传 family_id 为 null 或仅传 preset 为 null）：非法组合，返回 422 `INVALID_FONT_SOURCE_COMBINATION`。
  - **双非空**（同时传有效 family_id 与 preset）：互斥冲突，返回 422 `MUTUALLY_EXCLUSIVE_FONT_SOURCE`。
- 幂等与指纹策略：
  - PATCH 更新指纹使用版本化的显式字段集（`exclude_unset=True`），确保“省略保留”与“显式 null 清空”产生不同指纹；同键异载荷返回 409 `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`。
  - 创建沿用默认色板补全后的内部载荷指纹，同时兼容曾使用外部 DTO 指纹的已完成结果。更新兼容上一版部分字段指纹；对最早的全量指纹，只为不含显式 null 的输入重放已完成结果。兼容匹配不重新执行写入，不接管未完成记录。
  - 最早的全量指纹没有保存字段存在性，无法安全区分旧 null 请求的意图，此类输入保留 409；调用方应先查询目标核对结果，不能自动更换 key 重发。新版本记录不走这类有歧义的匹配。
- 数据迁移与共享样例：
  - 经评估，现有 `workspace_themes`、`workspace_font_families`、`workspace_font_configs` 表与唯一约束已完备，无需新增数据库表或迁移脚本。
  - 完整正反例与共享契约测试用例位于主仓 `tests/fixtures/cli-font-theme/font-theme-contract-cases.json`。

### 5.2 页面和组件重任务

页面、组件源码创建和编辑不得在外部接入层直接写数据库或启动 Runtime。必须使用持久化 Mutation Job：

```text
POST /api/v1/jobs/mutations/pages
POST /api/v1/jobs/mutations/pages/edits
POST /api/v1/jobs/mutations/components
POST /api/v1/jobs/mutations/components/edits
POST /api/v1/jobs/mutations/components/metadata
GET  /api/v1/jobs/mutations/{job_id}
POST /api/v1/jobs/mutations/{job_id}/cancel
POST /api/v1/jobs/mutations/{job_id}/retry
```

页面编辑必须携带当前版本基线；组件编辑必须携带草稿 hash 或主仓规定的等价乐观锁字段。外部客户端不得在 409 后静默覆盖重试。

### 5.3 预览地址

```text
POST /api/v1/projects/{project_id}/preview-artifact
POST /api/v1/pages/{page_id}/preview-artifact
```

两条接口都创建短期 preview artifact，并返回统一的 `PreviewArtifactResponse`，其中
`preview_url` 是可直接交给浏览器打开的预览地址。项目接口可以传入可选请求体
`{"route": "/overview"}` 指定入口路由；不传时使用项目默认入口。页面接口不要求
CLI 拼接源码模块路径，Backend 会根据页面当前的 `code` 和 `file_type` 解析单页面入口。

项目预览要求 `project:read + preview:run`，页面预览要求 `page:read + preview:run`。
预览地址和其中的签名上下文均为短期有效，客户端不应持久化或当作永久发布地址。

### 5.4 截图

页面创建与源码编辑的 Mutation 成功结果可包含 `result.screenshot`：`status` 为 `ready | pending | skipped`，`version_no` 为对应保存版本，`ready` 同时给出 `screenshot_id`、`width`、`height`；未就绪时给出 `reason_code`。`pending` 表示等待后续真实需求生成，不表示已经入队。客户端可忽略增量字段；字段缺失的旧响应继续沿用截图入口。

`ready` 图片可按页面范围内的内容 ID 直接下载；读取 latest 或模型视觉工具优先复用匹配版本和配置的图片。图片生成不表示模型已经看图，声音、交互和动画需另行验证。附图失败不会掩盖已成功的布局诊断，也不会自动立即再开浏览器。

校验警告和失败的 External 文本不包含内部工具名。需要明细时保留相同目标和原 `content/edits` 候选，设置 `detail=true`；创建失败且尚无 ID 时修正原候选重提。CLI 在本地补充 `wp page validate` / `wp component validate`，MCP 使用其注册的 `wp_validate_entity`。

```text
GET  /api/v1/pages/{page_id}/screenshot
```

截图任务由主仓通过预览队列完成；首版不暴露 Build 执行、构建状态、产物下载或 Restore operation。

需要等待明确任务终态或读取指定时间轴状态时使用异步截图任务：

```text
POST /api/v1/pages/{page_id}/screenshot-jobs
GET  /api/v1/pages/{page_id}/screenshot-jobs/{job_id}
GET  /api/v1/pages/{page_id}/screenshot-jobs/{job_id}/content
```

- 创建请求必须携带 `Idempotency-Key`，请求体包含 `viewport_width`、`viewport_height`，可选 `target_page_version_no` 与 `motion_snapshot`。目标版本与页面当前版本不一致时返回 409 `PAGE_SCREENSHOT_TARGET_VERSION_CONFLICT`，不会静默截取新版本。
- `motion_snapshot` 必须提供 `timeline_id`，并在 `at_ms` 与 `at_label` 中二选一；`offset_ms` 只能与 `at_label` 同时使用，`visual_mode` 为 `full | reduced`。当前 `timeline.capture_snapshot` 能力关闭，携带该字段返回 409 `TIMELINE_UNSUPPORTED`，不会降级成默认截图或只丢弃选择器重试。
- 不携带 `motion_snapshot` 的任务成功后按既有语义推进页面默认截图指针；携带 `motion_snapshot` 的临时任务只保存本次结果，不更新默认指针，也不会让读取 latest 的客户端拿到临时帧。显式选择器要求执行回执 `applied_motion.status=applied`，否则任务以 422 `TIMELINE_SNAPSHOT_UNAVAILABLE` 失败，不返回未采样截图。
- 状态响应包含 `status`、回显的 `motion_snapshot`、成功时的 `result`（`screenshot_id`、`content_url`、`version_no`、宽高与有界 `applied_motion`）和失败时的 `error`。任务必须属于路径中的页面，否则返回 404 `PAGE_SCREENSHOT_JOB_NOT_FOUND`。
- 内容接口仅在任务成功后返回 PNG，未成功返回 409 `PAGE_SCREENSHOT_JOB_NOT_READY`，不回退默认最新截图。响应携带 `X-Page-ID`、`X-Page-Version-No` 与 `X-Screenshot-Id`。
- 时间轴截图只提供指定时刻的静态视觉证据，`applied_motion` 描述采样状态，不代表声音已播放、动画已在用户设备上验证或 reduced 视觉模式符合预期；这些结论仍需真实预览或放映观察。

### 5.4 幂等和归档

- 所有会改变业务数据或创建、取消、人工重试任务的请求必须遵守 operation 注册表中的 `Idempotency-Key` 要求。相同 key、operation 和请求指纹重放首次响应；不同请求复用 key 返回 409；首个请求仍在执行时返回 409、`Retry-After` 和可重试标记。
- 校验等纯只读请求不应伪造写入幂等语义。
- 外部 Agent 只使用归档，不提供永久硬删除。
- 单对象归档和批量归档的确认、原子性、数量上限由主仓契约定义。
- 页面与项目归档统一写入 `status=archived`，不设置 `deleted_at`；单项与批量接口采用相同语义，归档对象仍可在 Editor 归档列表查询和恢复。
- 页面归档清理其路由绑定及因此产生的空分组，保留源码和版本；项目归档不级联归档或删除页面、路由及工作空间共享资产。
- 归档后的对象退出默认查询和操作边界；首版不提供 Restore operation。

## 6. 错误和状态

外部接入应保留 Backend 的业务错误码，不把所有失败压成通用异常。至少保持以下语义：

| 情况 | 外部客户端处理 |
|---|---|
| 401 | 未认证或 PAT 无效，不自动重试 |
| 403 | Scope 或工作空间授权不足 |
| 404 | 对象不存在或不属于当前空间 |
| 409 | 版本、草稿、状态或幂等冲突，重新读取后再决定 |
| 422 | 请求 Schema 或业务参数错误 |
| 429 | 仅按 `Retry-After` 和客户端策略有限重试 |
| 5xx/网络失败 | 仅对安全的幂等读操作有限重试 |
| Job 失败 | 保留 Job 状态、业务错误码和诊断摘要 |

Mutation 对外状态固定为 `pending | running | succeeded | failed | canceled`。`attempt_count` 表示已执行的自动重试次数，`max_attempts` 包含首次执行；自动重试沿用同一 `job_id`，人工重试创建新任务并通过 `retry_of_job_id` 关联原任务。running 取消是协作式取消，Worker 可以完成诊断，但必须在业务写入前收敛为 canceled。

## 7. 已知契约问题

页面/组件安全元数据 PATCH、Mutation 状态/取消/重试/幂等契约已冻结；首版明确排除 Build 执行、产物下载、Restore、图片能力和 Agent 运行。

## 8. 变更流程和测试归属

### 主仓变更

以下变更必须先在主仓完成：

- 路径、HTTP 方法、请求/响应 DTO；
- Scope、Header、幂等要求；
- 错误码、状态和取消语义；
- `/standards/*`、`/capabilities` 和 OpenAPI 字段；
- 版本、归档和工作空间隔离规则。

主仓至少运行：

```powershell
pnpm run test:contracts
```

### 客户端仓变更

以下内容分别在 `web-presentation-cli` 或 `web-presentation-mcp` 维护：

- CLI 命令名、Click 参数、Profile 和终端输出；
- 专用 API Client 的传输适配和轮询封装；
- MCP Tool、Resource、Prompt、传输和结构化结果；
- Skill 工作流和调用检查点；
- CLI / MCP 协议和仓内适配测试。

### 联动顺序

1. 主仓先修改并测试 External API 契约。
2. 主仓更新本文和对应 operation 注册表。
3. 主仓在 PR 或发布说明中标注需要升级的客户端仓适配。
4. `web-presentation-cli` 与 `web-presentation-mcp` 更新适配实现和测试。
5. 联调目标主仓版本，确认旧客户端兼容或明确最低版本。

## 9. 相关文档

- 主仓 CLI 集成边界：[docs/developer/cli.md](../cli.md)
- 主仓 MCP 集成边界：[docs/developer/mcp.md](../mcp.md)
- CLI 实施矩阵：[web-presentation-cli/docs/cli-capability-completion.md](https://github.com/LLMxPM/web-presentation-cli/blob/main/docs/cli-capability-completion.md)
- MCP 实施规划：[web-presentation-mcp/docs/mcp-implementation-plan.md](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/mcp-implementation-plan.md)
- 主仓 AI 工具规格：[docs/developer/backend/ai-tool-specs.md](../backend/ai-tool-specs.md)（仅平台内部 Agent，不作为 External API 契约）
