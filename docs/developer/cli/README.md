# CLI 技术方案

## 1. 文档状态

本文是 `web-presentation` 面向桌面 Agent 的 CLI 技术方案，基于平台重构后的**通用业务实体操作模型**（Generic Business Entities & Operations）、**统一自省与规范体系**和**工作空间安全底座**进行规划，用于确定模块边界、命令能力、认证方式、工作空间隔离和分阶段实施策略。

方案基于以下前提：

- 所有 LLM 自然语言推理、任务规划、图片生成和多模态理解均由调用方桌面 Agent（如 Antigravity、Claude Desktop、Cursor、Cline 等）自行完成。
- CLI 不内置 Agent，不调用平台内部 AI 会话（`AiAgentSession`），不管理大模型供应商和 API Key。
- CLI 是 Backend HTTP API（及面向外部的 External API v1）的客户端，不直接访问数据库、不直接调用 Runtime，也不导入 Backend 内部 Service。
- Skill 负责告诉 Agent 如何组织创作流程，CLI 负责提供确定、可组合、可自省、可审计的原子能力。
- 工作空间是 CLI 的强隔离边界；项目、页面、资源、组件、主题、样式、字体、Runtime Kit、任务和产物都必须归入且严格校验到单一工作空间。

## 2. 建设目标与非目标

### 2.1 建设目标

CLI 让具备 Shell 执行、文件读写和多模态查看能力的桌面 Agent 完成以下标准化创作闭环：

```text
选择单一工作空间
  -> 动态查询代码规范 (wp standards) 与操作手册 (wp guide)
  -> 读取项目、主题、样式、资源、组件和 Runtime Kit 上下文
  -> 在调用方生成页面/组件源码与视觉素材
  -> 上传资源并创建/修改页面或组件源码（携带乐观锁基线）
  -> 执行 Compact 代码检查与诊断 (wp validate)
  -> 创建截图任务、等待并下载截图 (wp screenshot wait/download)
  -> 调用方多模态视觉复核，进入迭代循环
  -> 创建页面快照 (wp page snapshot)
  -> 触发项目构建并下载产物包 (wp build wait/download)
```

CLI 核心特性要求：

- **统一实体契约**：基于平台统一实体模型，支持对 8 种核心资源（`project`, `page`, `component`, `asset`, `theme`, `style`, `runtime_kit`, `font`）的正交操作与响应解析。
- **规范与自省发现**：直接从服务端动态拉取当前生效的代码规范（Markdown）与操作参数 Schema，杜绝外部 Skill 提示词与服务端校验规则漂移。
- **精简紧凑的校验反馈**：代码检查默认输出 Compact 诊断结论（摘要、布局数值、最多 10 条带定位的问题），支持按需展开 `--detail`。
- **生命周期收敛（Archive First）**：废除硬删除，全面统一为归档语义；单项直接归档，批量原子确认，保护资产安全。
- **机器可读与大文件友好**：所有业务命令支持机器稳定读取的 JSON 输出；大段源码和二进制文件通过文件或 stdin/stdout 传递。
- **并发控制与幂等重试**：写操作强制校验工作空间断言与版本并发基线（`base_version_no` / `source_hash`），支持 `Idempotency-Key`。
- **统一长任务体验**：截图、构建等异步长任务使用统一的退避轮询、等待与优雅取消机制。
- **安全凭证生命周期**：采用 Personal Access Token (PAT) 认证，支持工作空间显式授权、细粒度 Scopes、有效权限交集与主动吊销。

### 2.2 非目标

- 自然语言对话入口，例如 `wp agent run`。
- 平台内部 AI session、run、SSE 消息、requirement 或工具确认恢复。
- 服务端 Chat 模型配置、图片生成模型配置或 API Key 管理。
- MCP Server（未来可作为独立适配层接入，不属于 CLI 核心）。
- CLI 直接连接底层数据库、Redis 或对象存储。
- 自动化跨工作空间写入或默认全局跨空间搜索。
- 破坏性永久硬删除操作（无 `wp delete` 命令）。

## 3. 总体架构

```text
桌面 Agent + web-presentation Skill
              |
              | 进程调用、JSON 输出、文件 I/O
              v
        web-presentation CLI (wp)
              |
              | HTTPS + Bearer Token (PAT) + X-WP-Workspace-ID
              v
    Backend API / External API v1
              |
              +--> 通用实体路由 / 操作模型 (operation_models.py)
              +--> 代码规范服务 (Code Standards) / 操作手册 (Tool Specs)
              +--> 代码检查与诊断服务 (CodeCheckService / Chromium 池)
              +--> 权限与工作空间校验 (DeliveryAccessContext / Token Grants)
              +--> 截图与构建异步任务队列 (PageScreenshotJob / BuildJob)
              +--> Runtime Kit Manifest 与版本化公共能力
```

CLI 作为一个独立的 Python 包 `cli/` 维护，使用 `uv` 进行依赖和虚拟环境管理，命令名为 `wp`：

```text
cli/
├── pyproject.toml
├── src/web_presentation_cli/
│   ├── main.py
│   ├── client/               # HTTP Client、PAT 鉴权、Workspace Assertion、上传下载
│   │   ├── base.py
│   │   ├── entity_client.py  # 统一实体操作核心客户端
│   │   ├── standards_client.py
│   │   └── jobs_client.py
│   ├── commands/             # Typer 命令行参数解析与子命令组
│   │   ├── auth.py
│   │   ├── context.py
│   │   ├── standards.py
│   │   ├── guide.py
│   │   ├── entities.py       # 通用实体操作命令
│   │   ├── aliases/          # 友好资源别名 (page, component, asset, project...)
│   │   ├── validate.py
│   │   ├── screenshot.py
│   │   └── build.py
│   ├── config/               # Profile 配置、凭证安全存储
│   ├── output/               # JSON Envelope 解包、Compact 诊断格式化、错误渲染
│   └── errors/               # 错误码与退出码映射
└── tests/
```

### 3.1 技术栈选型

- **语言环境**：Python 3.11 及以上。
- **包管理与构建**：`uv` 管理依赖、虚拟环境和 CLI 工具发布。
- **命令行框架**：`Typer`（结合 `Rich`）组织多级命令、类型提示与自动帮助文档。
- **HTTP 通信**：`httpx` 处理 HTTP/2、连接池、超时控制与大文件流式上传下载。
- **数据与契约**：`Pydantic v2` 定义 CLI 配置、统一 Envelope 和稳定 JSON DTO。
- **凭证存储**：`keyring` 保存在系统凭证库；无 GUI/CI 环境通过 `WP_TOKEN` 环境变量传入。

选型优势：
- 契约高度复用：CLI DTO 可直接对齐 Backend 的 `operation_models.py` 与 `tool_specs.py`。
- 工程一致性：完全契合仓库根目录的 Python + `uv` 规范，Backend 开发者可直接维护和编写契约测试。

分发与安装方式：

```powershell
uv sync --project cli
uv run --project cli wp --help
uv tool install web-presentation-cli
```

## 4. 认证与凭证模型

### 4.1 Personal Access Token (PAT)

CLI 采用 Personal Access Token 作为标准凭证，不依赖浏览器 Session Cookie：

```text
api_access_tokens
- id
- user_id
- name
- token_prefix          # 明文前缀，用于列表展示与快速定位 (如 wp_pat_...)
- token_hash            # 安全哈希（Argon2 / SHA-256）
- expires_at            # 过期时间（必须设定）
- last_used_at          # 最近使用时间（受控节流更新）
- revoked_at            # 吊销时间
- created_at

api_access_token_workspaces
- token_id
- workspace_id          # 显式授权的工作空间（支持 1 到多个，默认单个）

api_access_token_scopes
- token_id
- scope                 # 授予的操作范围
```

核心安全约束：
1. 数据库仅存储 Token 哈希；Token 明文只在创建时向用户展示一次。
2. Token 必须指定过期时间，且支持随时在控制台或 CLI 中主动吊销。
3. 单空间优先：默认创建单工作空间 Token；跨空间 Token 必须显式枚举目标工作空间，不提供全局通配。
4. **有效权限取严格交集**：
   ```text
   有效权限 = 用户账号处于激活状态 (active)
             ∩ 用户在目标工作空间中持有有效成员身份 (active membership)
             ∩ Token 的授权工作空间包含当前目标工作空间 (workspace grants)
             ∩ Token 的 Scopes 包含当前请求所需的操作范围
             ∩ 用户在工作空间中的角色角色 (owner / member) 允许当前动作
   ```
5. 任何一条不满足，Backend 一律拒绝。用户被移出工作空间或账号停用时，Token 立即失效。

### 4.2 粗粒度 Scopes 清单

| Scope | 涵盖操作与能力 |
| :--- | :--- |
| `workspace:read` | 查看工作空间基本信息、成员列表及当前授权范围 |
| `project:read` | 读取项目元数据、路由树、配置与构建摘要 |
| `project:write` | 创建、修改项目，整树覆盖路由，应用样式，归档项目 |
| `page:read` | 读取页面元数据、页面源码、版本历史、依赖与截图状态 |
| `page:write` | 创建页面、提交源码（乐观锁）、更新元数据、创建快照、归档页面 |
| `asset:read` | 读取资源元数据、标签、预览资源内容与下载二进制文件 |
| `asset:write` | 上传资源、保存内容更新、更新元数据、归档资源 |
| `component:read` | 读取组件元数据、组件源码、版本历史、依赖与预览配置 |
| `component:write` | 创建组件、提交组件源码（乐观锁）、发布组件新版本、归档组件 |
| `design-system:read` | 读取主题（色板）、样式配置、字体列表和 Runtime Kit Manifest |
| `design-system:write` | 创建与修改主题色板、样式快照配置，归档主题与样式 |
| `preview:run` | 触发代码静态校验与真实渲染检查 (`validate`)、创建预览 artifact 与截图任务 |
| `build:run` | 创建项目构建任务、查询构建状态与下载发布产物包 |

> [!NOTE]
> 平台已废除永久硬删除，因此不再设立 `dangerous:delete` Scope；资产清理统一通过归档（`*:write`）进行受控治理。

## 5. 工作空间隔离与资产治理

### 5.1 强隔离原则

CLI 的“当前工作空间”仅是本地减少重复输入的便捷上下文，不能作为服务端的授权信任凭据。

```text
调用方发起请求
  -> 请求携带 PAT Bearer Token + X-WP-Workspace-ID 断言
  -> Backend 校验 Token 有效性、Token workspace grant 与 active membership
  -> Backend 从数据库反查目标对象 (Project/Page/Asset/Component/Job) 真实 workspace_id
  -> 验证：请求断言 == 对象真实 workspace_id == Token grant == Member 空间
```

1. **工作空间断言**：除 `auth`、`version`、`capabilities` 外，所有业务请求必须显式携带 `X-WP-Workspace-ID`。
2. **完整归属链校验**：访问页面时，Backend 同时校验 `page.project_id` 与 `project.workspace_id` 是否完全匹配断言。
3. **防止越权探测**：无权访问的对象，外部 API 统一返回 `404 OBJECT_NOT_FOUND`，杜绝通过 `403` 枚举其它工作空间的存在性。
4. **命名空间隔离**：异步任务（截图、构建）、缓存键与幂等记录均包含 `workspace_id` 前缀，禁止跨工作空间复用。

### 5.2 资产治理：归档优先（Archive First）

- 平台内容助手与外部 CLI 均**不提供永久硬删除命令**。
- 清理项目、页面、组件、资源、主题和样式统一使用 `archive`：
  - **单项归档**：免二次交互确认，直接标记为归档状态。
  - **批量归档**（2～100 个）：要求显式确认（CLI 需提供 `--yes` 或交互确认），以整批原子语义执行。
  - **无级联归档**：项目归档不会级联归档页面、路由或工作空间共享资产。
- 归档后的对象在常规列表中不可见，但在需要时可通过管理端或恢复接口还原。

### 5.3 双通道交付鉴权（DeliveryAccessContext）

资源文件、页面截图与构建站点产物必须经过鉴权保护，杜绝未鉴权的匿名下载：

```text
1. 用户 / CLI 下载通道：
   携带 PAT Bearer Token -> 校验 active membership + Token grant + 对象 workspace 归属 -> 返回内容

2. Runtime 内部回源通道：
   携带短期 Runtime service token (绑定 preview/build artifact) -> Backend 校验 owner_scope -> 允许回源
```

## 6. 通用交互契约与输出

### 6.1 输出约束

- 所有的业务命令均支持 `--json` 开关。
- 标准输出（`stdout`）在 `--json` 模式下**只输出且严格输出一个合法的 JSON 文档**；所有诊断日志、进度条和调试信息一律写入标准错误（`stderr`）。

统一响应 Envelope 结构（与平台通用业务模型保持一致）：

```json
{
  "success": true,
  "resource_type": "page",
  "operation": "update",
  "action": "content",
  "message": "页面源码更新成功。",
  "effect": "update",
  "mutation": {
    "kind": "page",
    "resource_type": "page",
    "operation": "update",
    "action": "content",
    "target": { "id": 35, "version_no": 8 }
  },
  "data": {
    "id": 35,
    "current_version_no": 8,
    "source_hash": "a1b2c3d4..."
  },
  "context": {
    "workspace_id": 3,
    "project_id": 12
  },
  "request_id": "req-987654321"
}
```

失败响应 Envelope 结构：

```json
{
  "success": false,
  "error": {
    "code": "PAGE_VERSION_CONFLICT",
    "message": "页面版本已发生变化，提交被拒绝。",
    "recoverable": true,
    "hint": "请拉取最新页面源码并在当前基线上重新提交。",
    "details": {
      "expected_base_version": 7,
      "current_remote_version": 8
    }
  },
  "request_id": "req-987654321"
}
```

稳定退出码表：

| 退出码 | 含义 | 场景示例 |
| :---: | :--- | :--- |
| `0` | 成功 (SUCCESS) | 命令正常执行并返回 |
| `2` | 参数错误 (INVALID_ARGUMENTS) | 缺少必填参数、参数格式非法、互斥选项同时出现 |
| `3` | 认证失败 (UNAUTHENTICATED) | Token 缺失、已过期、已吊销或无效 |
| `4` | 权限拒绝 (PERMISSION_DENIED) | Scope 不足、未授权该工作空间、角色限制 |
| `5` | 对象不存在 (NOT_FOUND) | 目标 ID 在当前工作空间不存在 |
| `6` | 并发/状态冲突 (CONFLICT) | 乐观锁版本不一致、幂等冲突、草稿状态冲突 |
| `7` | 服务不可用 (UNAVAILABLE) | Backend 或 Runtime 暂时不可达 |
| `8` | 异步任务超时/失败 (TASK_FAILED) | 截图失败、构建失败或等待超时 |
| `10` | 内部错误 (INTERNAL_ERROR) | 未分类的系统异常 |

### 6.2 输入与并发约束

- **大段源码与配置文件**：使用 `--file <path>` 或 `--stdin` 传入，不作为命令行长参数。
- **二进制资产**：通过 `--file <path>` 指定本地文件进行流式上传。
- **乐观锁控制**：更新页面或组件源码必须提供 `--base-version <int>` 或 `--source-hash <str>`，拒绝静默覆盖。
- **幂等保护**：创建对象和发起长任务支持 `--idempotency-key <key>`，防止超时重试产生重复记录。

## 7. 命令能力规划

CLI 命令划分为**基础与认证**、**动态规范与自省**、**通用业务实体操作**、**代码校验与诊断**、**长任务流水线**五大板块。

### 7.1 基础、配置与认证

| 命令 | 阶段 | 所需 Scope | 说明 |
| :--- | :---: | :--- | :--- |
| `wp version` | MVP | 无 | 输出 CLI 版本、协议版本及环境信息 |
| `wp capabilities` | MVP | 无 | 返回服务端功能开关、最大文件限制与支持的资源类型 |
| `wp health` | MVP | 无 | 快速检查 Backend 服务可达性 |
| `wp profile <add\|list\|show\|use\|remove>` | MVP | 无 | 管理本地连接配置（Server URL、默认 Workspace 等） |
| `wp context show` | MVP | 无 | 打印当前生效的 Server、Workspace、Token 状态与上下文 |
| `wp auth login` | MVP | 无 | 交互式生成并保存受限 PAT |
| `wp auth whoami` | MVP | 无 | 查看当前用户、Token 有效期、授权工作空间与 Scopes |
| `wp auth logout` | MVP | 无 | 清除本地保存的凭证，可选向服务端发起主动吊销 |
| `wp workspace <list\|get\|use>` | MVP | `workspace:read` | 查看授权工作空间列表与详情，切换本地默认工作空间 |
| `wp token <create\|list\|revoke>` | 后续 | `owner` 角色 | 自动化 Token 生命周期管理 |

### 7.2 动态规范与操作自省（对齐平台自省机制）

外部桌面 Agent 通过这两个命令动态了解当前工作空间生效的代码编写规范与业务操作参数，无需外部提示词硬编码。

| 命令 | 阶段 | 所需 Scope | 说明 |
| :--- | :---: | :--- | :--- |
| `wp standards page` | MVP | `page:read` | 获取当前生效的**页面代码规范 Markdown**（包含 Runtime Kit 引入要求、Vue 模板限制等） |
| `wp standards component` | MVP | `component:read` | 获取当前生效的**组件代码规范 Markdown**（包含 Props 定义、previewSchema 结构等） |
| `wp guide` | MVP | 已认证用户 | 罗列当前支持的全部通用操作键（`operation_key`）索引与风险说明 |
| `wp guide <operation_key>` | MVP | 已认证用户 | 查询特定操作（如 `page.update.content`）的**精确参数 JSON Schema**、前置条件、副作用和调用示例 |

### 7.3 通用业务实体操作（Core Entities）

CLI 底层由统一的 `EntityClient` 驱动，同时提供清晰的**直观别名命令**：

#### 项目（Project）
- `wp project list`：罗列当前工作空间的项目（支持分页与关键词过滤）。
- `wp project get <ID>`：读取项目详情、配置与路由摘要。
- `wp project create --name <NAME> [--theme-id <ID>]`：创建新项目。
- `wp project update <ID> [--name <NAME>] [--configuration <JSON_FILE>]`：更新项目元数据或配置。
- `wp project routes get <ID>`：获取项目当前路由树。
- `wp project routes replace <ID> --file <ROUTES_JSON> --base-version <V>`：整树覆盖项目路由（强制并发基线）。
- `wp project apply-style <ID> --style-id <STYLE_ID>`：将指定样式快照应用到项目。
- `wp project archive <ID...>`：归档项目（单项免确认，批量 `--yes`）。

#### 页面（Page）
- `wp page list --project-id <PID>`：罗列项目下的页面列表。
- `wp page get <ID>`：读取页面详情、依赖和配置。
- `wp page source pull <ID> [--output <FILE>]`：拉取页面 Vue 源码，并返回当前版本号与源码哈希。
- `wp page create --project-id <PID> --name <NAME> --route-path <PATH> [--file <PAGE_VUE>]`：创建新页面。
- `wp page source push <ID> --file <PAGE_VUE> --base-version <V>`：更新页面源码（必须提供并发基线，服务端自动触发实时编译与校验）。
- `wp page update <ID> [--name <NAME>] [--route-path <PATH>]`：更新页面基本元数据。
- `wp page snapshot <ID> [--label <LABEL>]`：为当前页面创建正式快照版本。
- `wp page versions list <ID>`：读取页面的历史快照列表。
- `wp page archive <ID...>`：归档页面。

#### 组件（Component）
- `wp component list [--scope suggested|all]`：查询工作空间组件库（支持建议组件筛选）。
- `wp component get <ID> [--view detail|source|versions]`：读取组件详情、Vue 源码或版本历史。
- `wp component create --name <NAME> --type <TYPE> --file <COMP_VUE> --preview-schema <SCHEMA_JSON>`：创建新组件草稿。
- `wp component source push <ID> --file <COMP_VUE> --base-version <V>`：提交组件源码更新（自动触发编译与场景渲染检查）。
- `wp component publish <ID>`：执行生命周期发布动作（`component.action.publish`），生成正式可用版本。
- `wp component archive <ID...>`：归档组件。

#### 资源（Asset）
- `wp asset list [--scope suggested|all] [--tag <TAG>]`：查询工作空间资源库。
- `wp asset upload --file <LOCAL_FILE> [--name <NAME>] [--tags <T1,T2>]`：上传静态图片/文件至工作空间资源库。
- `wp asset pull <ID> [--output <FILE>]`：读取可编辑资源（如 SVG、文本）的源码内容。
- `wp asset push <ID> --file <FILE>`：更新可编辑资源的内容。
- `wp asset download <ID> --output <FILE>`：通过受保护的交付鉴权通道安全下载资源二进制文件。
- `wp asset archive <ID...>`：归档资源。

#### 设计系统与公共资产（Design System & Runtime Kit）
- `wp theme list` / `wp theme get <ID>`：读取主题色板配置。
- `wp theme update <ID> --colors <JSON_FILE>`：修改主题色板（仅限颜色配置，不暴露 Logo/字体）。
- `wp style list` / `wp style get <ID>`：读取样式快照配置。
- `wp font list`：读取工作空间可用字体库。
- `wp runtime-kit list` / `wp runtime-kit get <NAME>`：查询 Runtime Kit 公共组件与版本化导出清单（如 `<ExportName>.v1`）。
- `wp runtime-kit manifest`：获取完整的公开能力 Manifest。

### 7.4 代码检查与差异预览（对齐 Compact 校验机制）

对齐平台 `validate_entity` 的 4 种检查模式与精简输出机制：

| 命令 | 模式 (Mode) | 阶段 | 说明 |
| :--- | :---: | :---: | :--- |
| `wp validate page <ID> [--detail]` | `current` | MVP | 检查当前已保存页面的 Runtime 编译、真实渲染与布局溢出问题 |
| `wp validate page --project-id <PID> --file <PAGE_VUE> [--detail]` | `content` | MVP | 预检一段新页面候选源码，不落库 |
| `wp validate page <ID> --edits <JSON_FILE> [--detail]` | `edits` | MVP | 预检针对现有页面的局部结构化编辑，不落库 |
| `wp validate component <ID> [--detail]` | `current` | MVP | 检查当前组件在各预设 scenario 下的真实渲染与布局情况 |
| `wp validate component --file <COMP_VUE> --preview-schema <JSON> [--detail]` | `content` | MVP | 预检新组件候选源码及其 previewSchema |
| `wp validate asset <ID> --file <NEW_CONTENT>` | `preview` | MVP | 预览可编辑资源内容更新后的 unified diff，不落库 |

> [!TIP]
> 默认输出精简的 Compact 文本结论（包含摘要、布局数值、最多 10 条带定位的警告与建议），极度适合 Agent 上下文消费；使用 `--detail --json` 时输出完整结构化诊断事实。

### 7.5 预览、截图与构建长任务

| 命令 | 阶段 | 所需 Scope | 说明 |
| :--- | :---: | :--- | :--- |
| `wp preview create --project-id <PID>` | MVP | `preview:run` | 生成临时预览 Artifact 与带签名的预览上下文 Token |
| `wp screenshot <PAGE_ID> [--output <FILE>]` | MVP | `page:read`, `preview:run` | 获取指定页面的最新 PNG 截图（自动触发服务端队列刷新，下载后原子落盘） |

| `wp build start --project-id <PID>` | MVP | `build:run` | 提交项目打包构建任务，返回 `job_id` |
| `wp build status <JOB_ID>` | MVP | `build:run` | 查看构建进度与日志摘要 |
| `wp build wait <JOB_ID> [--timeout 180]` | MVP | `build:run` | 轮询等待构建完成 |
| `wp build download <JOB_ID> --output <ZIP_FILE>` | MVP | `build:run` | 下载最终静态发布产物 Zip 包 |

## 8. Skill 与 CLI 的协同契约

配套的桌面 Agent Skill（如 `web-presentation.skill.yaml` 或 Antigravity Skill）设计原则：

- **自适应发现**：Skill 不再硬编码页面/组件代码规范，而是指示 Agent 在每轮创作开始时：
  1. 运行 `wp context show --json` 确认当前工作空间与项目上下文。
  2. 运行 `wp standards page` 或 `wp standards component` 动态拉取当前版本规范。
  3. 不确定参数时运行 `wp guide <op>` 获取字段定义。
- **创作与视觉循环（Visual Feedback Loop）**：
  ```text
  Agent 编写代码 -> wp validate 预检 -> wp page source push 提交
  -> wp screenshot start + wait -> wp screenshot download
  -> Agent 查看本地图片视觉复核 -> 针对排版/样式问题进行下一轮迭代
  ```
- **错误恢复指导**：
  - 遇到 `PAGE_VERSION_CONFLICT`（退出码 6）：指示 Agent 重新执行 `wp page source pull` 并在最新基线上合并修改。
  - 遇到 `CODE_CHECK_FAILED`：解析返回的定位与 hint 修复 Vue 源码。

## 9. Backend 需提供的接口契约

为了支撑上述 CLI 能力，Backend 需确保开放以下稳定外部接口（建议挂载在 `/api/external/v1` 下或复用统一鉴权后的路由）：

1. **PAT 认证与审计**：`/api/external/v1/auth/tokens`（创建、校验、吊销、工作空间授权校验）。
2. **规范与自省接口**：
   - `GET /api/external/v1/standards/{standard_type}`：返回 `page` 或 `component` 规范 Markdown。
   - `GET /api/external/v1/guides` & `GET /api/external/v1/guides/{operation_key}`：返回操作手册与 JSON Schema。
3. **统一通用实体端点**：
   - `POST /api/external/v1/entities/list`
   - `POST /api/external/v1/entities/get`
   - `POST /api/external/v1/entities/create`
   - `POST /api/external/v1/entities/update`
   - `POST /api/external/v1/entities/archive`
   - `POST /api/external/v1/entities/validate`
   - `POST /api/external/v1/entities/action`
4. **统一交付鉴权（DeliveryAccessContext）**：
   - 静态资源下载、页面截图获取、构建产物包下载统一接入 PAT Bearer / Cookie 鉴权。
5. **异步任务端点**：
   - 截图任务创建、查询与取消（`/api/external/v1/jobs/screenshots/...`）。
   - 构建任务创建、查询与取消（`/api/external/v1/jobs/builds/...`）。

## 10. 测试方案

### 10.1 Backend 契约与安全测试
- PAT 哈希校验、过期、主动吊销与 Scopes 权限组合测试。
- 双工作空间隔离测试：使用 Workspace A 的 Token 访问 Workspace B 的实体必定返回 404。
- Workspace Assertion 冲突拒绝测试（`X-WP-Workspace-ID` 与对象实际空间不符）。
- 乐观锁并发冲突测试（携带旧 `base_version_no` 提交被拒绝）。
- 交付鉴权测试：匿名访问资源/截图/产物被拒绝，有效 PAT / Cookie 允许下载。
- 批量归档原子事务与确认保护测试。

### 10.2 CLI 单元与集成测试
- Profile 切换与工作空间解析优先级测试（显式参数 > 环境变量 > Profile 默认）。
- 统一 EntityClient 请求封装、Envelope 解包与退出码映射测试。
- 标准输出纯 JSON（`stdout`）与日志分离（`stderr`）测试。
- 大文件/源码流式上传与原子覆盖写入测试。
- 长任务退避轮询与优雅取消（Ctrl+C）测试。
- 凭证安全测试：日志与异常输出绝对不包含 Token 明文。

### 10.3 E2E 创作闭环验证
在预设的沙箱环境中完成端到端验证：
1. `wp auth login` 使用 PAT 完成认证并选定 Workspace 1。
2. 调用 `wp standards page` 动态获取规范。
3. 调用 `wp page create` 创建页面并提交源码。
4. 调用 `wp validate page` 确认无布局溢出。
5. 调用 `wp screenshot start` + `wp screenshot wait` 并下载截图。
6. 调用 `wp page snapshot` 创建快照。
7. 调用 `wp build start` + `wp build wait` 并下载构建产物 Zip 包。
8. 验证跨工作空间探测均被安全拦截。

## 11. 分阶段实施路线图

```text
阶段 0：规范确认与安全基础 (Security & Foundations)
  ├── 落地 PAT 数据库模型与哈希存储 (api_access_tokens)
  ├── 统一 Bearer PAT 与 Session Cookie 鉴权解析 (DeliveryAccessContext)
  └── 补齐 Workspace Assertion (X-WP-Workspace-ID) 强制校验中间件

阶段 1：外部 API v1 与自省契约 (Backend External API v1)
  ├── 开放动态代码规范端点 (/api/external/v1/standards/...)
  ├── 开放自省操作手册端点 (/api/external/v1/guides/...)
  └── 暴露基于 operation_models 的通用实体操作路由 (list, get, create, update, archive, validate, action)

阶段 2：CLI MVP 核心与自省只读 (CLI Read & Self-Discovery)
  ├── 搭建 cli/ Python 工程脚手架 (uv, Typer, httpx, Pydantic)
  ├── 实现 profile, auth, context, standards, guide 命令
  └── 实现项目、页面、组件、资源、主题、Runtime Kit 的通用实体查询命令

阶段 3：完整创作闭环 (CLI Write & Visual Review)
  ├── 实现带乐观锁的页面/组件源码提交 (push)
  ├── 实现 Compact 校验命令 (wp validate)
  ├── 实现受控的单项与批量归档 (wp archive)
  ├── 实现资源上传与受保护下载
  └── 实现截图与构建长任务的启动、轮询等待与产物下载

阶段 4：生态与桌面 Agent 适配 (Skill & Agent Integration)
  ├── 编写面向桌面 Agent 的 web-presentation Skill 指南
  ├── 对接 Antigravity / Claude Desktop 进行真实复杂 PPT 页面创作评测
  └── 优化错误恢复提示与离线包导出能力
```

## 12. 验收标准

1. **零平台模型依赖**：外部桌面 Agent 仅依靠 CLI 和本地多模态能力，即可独立完成从页面创建、代码编写、校验、视觉复核到打包交付的完整闭环。
2. **规范动态对齐**：通过 `wp standards` 和 `wp guide` 获取平台最新规则，避免客户端逻辑漂移。
3. **强安全隔离**：跨工作空间尝试 100% 拦截，资源与截图无匿名泄漏风险。
4. **并发与版本安全**：源码更新严格防覆盖，网络重试具备幂等保证。
5. **生命周期稳健**：全流程归档替代硬删除，误操作风险降至最低。
