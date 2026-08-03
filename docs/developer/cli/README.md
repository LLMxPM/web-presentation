# CLI 技术方案

## 1. 文档状态

本文是 `web-presentation` 面向桌面 Agent 的 CLI 技术方案，当前仅用于确定边界、命令能力、认证方式、工作空间隔离和实施顺序，不代表相关接口已经实现。

方案基于以下前提：

- 所有 LLM 推理、任务规划、图片生成和图片理解均由调用方 Agent 完成。
- CLI 不内置 Agent，不调用平台 AI 会话，不管理模型供应商和 API Key。
- CLI 是 Backend HTTP API 的客户端，不直接访问数据库、不直接调用 Runtime，也不导入 Backend 内部 Service。
- Skill 负责告诉 Agent 如何完成创作流程，CLI 负责提供确定、可组合、可审计的原子能力。
- 工作空间是 CLI 的强隔离边界；项目、页面、资源、组件、主题、样式、任务和产物都必须归入且校验到一个工作空间。

## 2. 建设目标与非目标

### 2.1 建设目标

CLI 第一阶段要让具备 Shell、文件读写和图片查看能力的桌面 Agent 完成以下闭环：

```text
选择单一工作空间
  -> 读取项目、主题、样式、资源、组件和 Runtime Kit 上下文
  -> 在调用方生成页面源码和图片
  -> 上传资源并创建或修改页面
  -> 执行确定性代码检查
  -> 创建截图任务并下载截图
  -> 调用方视觉复核并继续修改
  -> 创建页面快照
  -> 创建项目构建任务并下载产物
```

CLI 还应满足：

- 所有业务命令支持机器稳定读取的 JSON 输出。
- 大段源码和二进制内容通过文件或 stdin/stdout 传递。
- 写操作支持工作空间断言、版本并发控制和幂等重试。
- 截图、构建等长任务使用统一的查询、等待和取消体验。
- 身份凭证可吊销、可过期，并限制到明确的工作空间和操作 scope。
- Windows、Linux 和 macOS 使用相同的参数语义，不依赖特定 Shell 的转义行为。

### 2.2 非目标

第一阶段不包含：

- 自然语言对话入口，例如 `wp agent run`。
- AI session、run、SSE 消息、requirement 或工具确认恢复。
- Chat、图片生成和图片理解模型配置。
- MCP Server。
- CLI 直接连接数据库或对象存储。
- 自动替用户决定跨工作空间复制、发布或删除。
- 用 Skill 或 CLI 参数代替 Backend 权限校验。

## 3. 总体架构

```text
桌面 Agent + web-presentation Skill
              |
              | 进程调用、JSON、文件
              v
        web-presentation CLI
              |
              | HTTPS + Bearer Token
              v
          Backend API
              |
              +--> Service / Repository / Database
              +--> 截图队列 / Chromium 池
              +--> Runtime 预览与构建
              +--> 对象存储
```

建议新增独立 Python 包 `cli/`，使用 `uv` 管理，命令名暂定为 `wp`：

```text
cli/
├── pyproject.toml
├── src/web_presentation_cli/
│   ├── main.py
│   ├── commands/
│   ├── client/
│   ├── config/
│   ├── output/
│   └── errors/
└── tests/
```

模块职责：

- `commands/`：参数解析与用户交互，不承载业务规则。
- `client/`：Backend API Client、认证头、上传下载和轮询。
- `config/`：profile、默认工作空间和本地非敏感配置。
- `output/`：JSON、文本、文件输出和 stdout/stderr 约束。
- `errors/`：HTTP 错误到稳定退出码的映射。

CLI 与 Backend 的接口契约应显式版本化。可以继续复用现有 `/api` 路由，但对 CLI 稳定开放的接口需要形成独立契约清单；如果现有 Editor API 演进频繁，则增加 `/api/external/v1` 适配层。不要让 CLI 依赖 Editor 私有字段或页面展示逻辑。

### 3.1 技术栈选型

CLI 确定使用 Python，不采用 Node.js。建议使用：

- Python 3.11 及以上。
- `uv` 管理依赖、虚拟环境、构建和工具安装。
- Typer 组织多级命令和参数帮助。
- `httpx` 处理 HTTP、文件上传下载和连接超时。
- Pydantic 定义 CLI 配置、API 响应和稳定 JSON 输出。
- 系统 keyring 保存长期 Token；无法使用 keyring 的 CI 环境使用 `WP_TOKEN`。

选型对比：

| 维度 | Python | Node.js |
| :--- | :--- | :--- |
| 与 Backend 技术栈一致 | FastAPI、Pydantic、httpx、`uv` 均可沿用团队经验 | 需要单独维护 TypeScript API 模型和发布链路 |
| 仓库规范 | 已明确 Python 使用 `uv` 和 venv | 前端已使用 pnpm，但 CLI 与 Editor 没有运行时耦合 |
| HTTP、JSON、上传下载 | `httpx` 和 Pydantic 足够，异步任务轮询实现直接 | `fetch` 和 TypeScript 同样可胜任 |
| 多级 CLI 体验 | Typer 成熟，类型声明可生成帮助 | Commander、oclif 等同样成熟 |
| 桌面 Agent 安装 | 可通过 `uv tool install` 或 `uvx` 隔离安装 | 可通过 npm/pnpm 全局安装 |
| 零运行时单文件分发 | 需要 PyInstaller 等额外打包 | 也需要 Node SEA、pkg 等额外打包 |
| 后续维护成本 | Backend 开发者可以直接维护，诊断脚本和测试风格一致 | 需要同时维护 Backend Python 与 CLI TypeScript 两套工程约束 |

选择 Python 的主要理由不是复用 Backend 内部代码，而是降低长期维护和契约实现成本。CLI 仍然只调用 HTTP API，不能导入 `backend/app`；API 模型可以从稳定 OpenAPI 契约生成或在 CLI 内维护最小 DTO。

Node.js 的主要优势是 npm 生态和部分桌面 Agent 已自带 Node，但本项目并不需要把 CLI 嵌入 Editor、Electron 或 VS Code 扩展，因此该优势不足以抵消第二套语言和构建链路。若以后 CLI 的主要分发形态变为 Editor 内置终端、Electron 应用或 Node SDK，再重新评估 TypeScript 实现。

开发和安装入口建议为：

```powershell
uv sync --project cli
uv run --project cli wp --help
uv tool install web-presentation-cli
```

## 4. 认证和凭证模型

### 4.1 目标方案

远程和长期使用采用 Personal Access Token，不把浏览器 Cookie 作为正式 CLI 凭证。建议新增：

```text
api_access_tokens
- id
- user_id
- name
- token_prefix
- token_hash
- expires_at
- last_used_at
- revoked_at
- created_at

api_access_token_workspaces
- token_id
- workspace_id

api_access_token_scopes
- token_id
- scope
```

约束：

- 数据库只保存 Token 哈希；Token 明文仅在创建时展示一次。
- Token 必须有过期时间，支持主动吊销。
- Token 默认只绑定一个工作空间。
- 多工作空间 Token 必须显式选择允许访问的工作空间，不提供隐式全空间通配权限。
- 平台管理员也不能仅凭平台角色绕过 Token 的工作空间 grant。
- 每次使用后更新 `last_used_at`，但需要节流，避免每个读请求都产生数据库写入。
- 日志、异常、诊断输出和 shell 补全不得打印 Token。

有效权限计算采用交集：

```text
有效权限
= 用户账号仍启用
∩ 用户仍是目标工作空间的 active 成员
∩ Token 显式授予目标工作空间
∩ Token scopes 包含当前动作
∩ 工作空间成员角色允许当前动作
```

其中任意条件不满足，都必须由 Backend 拒绝。用户被移出工作空间后，即使 Token 尚未过期，也应立即失去访问权。

### 4.2 建议 scopes

第一版使用面向领域的粗粒度 scopes：

| Scope | 能力 |
| :--- | :--- |
| `workspace:read` | 读取当前 Token 被授权的工作空间基础信息 |
| `project:read` | 读取项目、路由、构建摘要 |
| `project:write` | 创建和修改项目、修改路由 |
| `page:read` | 读取页面、版本、依赖和截图状态 |
| `page:write` | 创建、修改、快照和恢复页面 |
| `asset:read` | 读取资源元数据和可编辑内容 |
| `asset:write` | 上传、创建、修改和归档资源 |
| `component:read` | 读取组件、版本和依赖 |
| `component:write` | 创建、修改和发布组件 |
| `design-system:read` | 读取主题、样式和字体 |
| `design-system:write` | 修改主题和样式配置 |
| `preview:run` | 创建预览 artifact 和截图任务 |
| `build:run` | 创建构建任务和下载构建产物 |
| `dangerous:delete` | 删除页面、资源、组件和构建产物 |

删除类操作不应被普通 `*:write` 隐式覆盖。第一阶段给桌面 Agent 的默认 Token 不授予 `dangerous:delete`。

### 4.3 本地凭证保存

CLI profile 保存：

- Backend URL。
- 工作空间 ID 或 code。
- 默认项目 ID 或 code，可选。
- 输出格式和超时等非敏感设置。
- Token 的安全存储引用。

Token 优先保存在操作系统凭证库；CI 可通过 `WP_TOKEN` 环境变量传入。不得把 Token 明文写进项目目录、Skill、命令历史或普通 YAML 配置。

开发期可临时复用现有登录接口并保存 Cookie，但它只能作为过渡方案：Cookie 缺少独立 scope、工作空间 grant、吊销说明和面向自动化的生命周期管理。

## 5. 工作空间隔离设计

### 5.1 基本原则

CLI 的“当前工作空间”只是减少重复输入的交互上下文，不是授权依据。Backend 必须独立验证每一个请求。

每个工作空间对象都应遵循：

```text
调用身份 -> Token workspace grant -> active membership
                                     |
请求 workspace 断言 --------------> 对象真实 workspace_id
```

具体规则：

1. 除 `auth`、`version`、`capabilities` 和受限的 `workspace list` 外，所有业务命令必须解析出唯一工作空间。
2. CLI 必须把解析后的工作空间作为路径、查询参数或 `X-WP-Workspace-ID` 断言发送给 Backend。
3. Backend 必须从项目、页面、资源、组件、任务或产物记录反查真实 `workspace_id`。
4. 请求断言、对象真实工作空间、Token grant 和用户 active membership 必须全部一致。
5. 项目与页面同时出现时，Backend 还必须验证 `page.project_id` 和 `project.workspace_id` 的完整归属链。
6. 不能因为调用方知道另一个工作空间的数字 ID、业务 code、文件哈希或 job ID 就返回对象存在性信息。
7. 跨工作空间写入默认禁止；只有专门设计的导出/导入流程可以跨空间迁移内容。

### 5.2 CLI profile 隔离

推荐一个 profile 对应一个 Backend 和一个工作空间：

```powershell
wp profile add client-a --server https://example.com --workspace ws_client_a
wp profile add client-b --server https://example.com --workspace ws_client_b
wp profile use client-a
wp context show --json
```

工作空间解析优先级：

```text
显式 --workspace
> WP_WORKSPACE 环境变量
> 当前 profile 的 workspace
> 无法解析则拒绝执行
```

写操作的规则更严格：

- 非交互模式下没有工作空间就直接失败，不能自动选择“最近使用”工作空间。
- `--workspace` 与 profile 工作空间不一致时默认失败；只有显式 `--allow-profile-workspace-override` 才允许覆盖，并且 Token 仍需有对应 grant。
- 每个写操作的 JSON 结果都返回 `workspace_id`、`project_id`、目标对象 ID 和 request ID，便于 Agent 复核。
- Skill 应要求每轮创作开始时先执行 `wp context show --json`，但 Backend 安全不能依赖该步骤。

### 5.3 列表和搜索隔离

- `wp project list`、`wp page list`、`wp asset list`、`wp component list` 必须限定当前工作空间。
- CLI 不提供默认的跨工作空间全局搜索。
- `wp workspace list` 只返回 Token grant 与 active membership 的交集。
- 对无权访问的对象，外部 API 建议统一返回 `404 OBJECT_NOT_FOUND`，减少通过 `403` 枚举对象存在性的机会；管理端内部接口可保留更明确的诊断语义。
- 分页总数、标签聚合和建议列表也必须在工作空间过滤之后计算，不能泄漏其它空间数量。

### 5.4 任务、缓存和幂等隔离

截图、构建和其它异步任务必须在创建时持久化 `workspace_id`，后续按 `job_id` 查询、等待、取消或下载产物时重新校验工作空间，而不是只校验任务创建人。

缓存和幂等键必须带命名空间：

```text
cache:{workspace_id}:{resource_type}:{resource_id}:...
idem:{principal_id}:{workspace_id}:{command}:{idempotency_key}
```

同一个 `idempotency_key` 不能在不同工作空间复用同一结果。幂等记录应保存请求摘要；相同键对应不同请求内容时返回冲突。

### 5.5 文件与产物隔离

- 上传资源时由当前工作空间决定存储前缀，不能接受调用方传入任意存储路径。
- 下载资源、截图和构建产物必须先通过受保护 API 校验身份和工作空间，再返回内容或短期签名 URL。
- CLI 下载文件时使用临时文件写入，校验完成后再原子替换目标文件，避免失败留下半成品。
- 文件名只能影响下载展示名，不能影响对象存储 key 或本地服务器物理路径。

当前 `/public/assets/{workspace_id}/{file_hash}`、`/public/cached-assets/{workspace_id}/{file_hash}`、`/public/page-screenshots/{page_id}` 和 `/build-artifacts/{project_id}/{job_id}` 存在无用户鉴权的公开读取语义。资源、页面截图和构建站点确定改为需要鉴权，但第一阶段不引入完整的发布、分享链接或通用签名 URL 系统。

采用最小双通道鉴权：

```text
用户/CLI 访问
  -> 现有 Session Cookie 或 PAT Bearer Token
  -> active membership + Token grant + 对象 workspace 校验

Runtime 内部回源
  -> 现有短期 Runtime service token
  -> PreviewContextToken，或 service token 绑定的构建 artifact
  -> artifact/job/workspace 声明一致性校验
```

具体处理：

1. 保持现有资源、截图和构建站点 URL 结构，减少 Editor、Runtime 和已保存 manifest 的改动。
2. 给这些读取路由增加统一 `DeliveryAccessContext` 依赖，而不是分别实现三套鉴权。
3. 普通浏览器使用现有同站 Session Cookie；CLI 使用 PAT Bearer Token。
4. Runtime 预览和截图回源继续使用已经存在的 preview context 与 Runtime service token，不新增长期服务凭证。
5. Runtime 构建下载工作空间资源时，把当前已经持有且绑定 `artifact_id` 的 Runtime service token 一并放入资源请求；Backend 从该 artifact 的 `owner_scope` 反查工作空间并校验目标资源，不再引入另一种资源下载 Token。
6. 构建站点入口及其静态子资源要求用户 Cookie 或 PAT；“公开发布/匿名分享构建站点”不属于 CLI 第一阶段，需要时另建显式发布能力。
7. 页面截图要求用户 Cookie 或 PAT；CLI 下载优先走受保护 API，不依赖响应模型里的公开 URL。
8. 模板包临时资源等同类公开入口也要纳入统一审计，至少要求用户会话或与 artifact 匹配的短期预览上下文。

该方案不新增 OAuth、独立 Ticket 表、逐文件签名 URL、CDN 鉴权或分享链接管理，复杂度主要集中在一个 Backend 鉴权依赖和 Runtime 构建资源请求补充请求头。

需要注意：生产环境应继续通过同一 Gateway 域名提供 Editor、Backend 和 Runtime，使 `<img>`、字体和构建站点子资源能够自动携带同站 Cookie。跨域部署不是第一阶段目标；如未来必须跨域，再评估短期签名 URL 或资源代理。

### 5.6 成员角色

当前 `WorkspaceMemberRole` 已有 `owner` 和 `member`。权限规则确定为：`member` 除删除内容和管理 Token 外，其它权限与 `owner` 一致。

| 动作 | owner | member |
| :--- | :---: | :---: |
| 读取工作空间内容 | 是 | 是 |
| 创建和修改项目、页面、资源 | 是 | 是 |
| 修改主题、样式和项目路由 | 是 | 是 |
| 创建和发布组件 | 是 | 是 |
| 创建截图、预览和构建任务 | 是 | 是 |
| 删除内容、管理 Token | 是 | 否 |

删除包括页面、项目、资源、组件、主题、样式、构建产物等不可逆或难恢复操作；归档、创建快照和恢复历史版本不按删除处理，`member` 可以执行。Token 的创建、授权工作空间调整、scope 调整和吊销均只允许 `owner`。

Backend 应集中实现角色到操作的授权策略，CLI 只展示服务端返回的结果。`dangerous:delete` scope 不能让 `member` 越过角色限制，即有效权限始终取角色与 Token scope 的交集。

## 6. CLI 通用契约

### 6.1 输出约束

所有业务命令支持 `--json`，stdout 只输出一个 JSON 文档，日志和进度写入 stderr。

成功结果：

```json
{
  "success": true,
  "data": {},
  "context": {
    "workspace_id": 3,
    "project_id": 12
  },
  "request_id": "req-123"
}
```

失败结果：

```json
{
  "success": false,
  "error": {
    "code": "PAGE_VERSION_CONFLICT",
    "message": "页面版本已变化。",
    "recoverable": true,
    "hint": "重新拉取页面源码后再次提交。"
  },
  "request_id": "req-123"
}
```

建议退出码：

| 退出码 | 含义 |
| :---: | :--- |
| `0` | 成功 |
| `2` | CLI 参数错误 |
| `3` | 认证失败或凭证过期 |
| `4` | 权限或工作空间隔离拒绝 |
| `5` | 对象不存在 |
| `6` | 版本、幂等或状态冲突 |
| `7` | Backend/Runtime 暂时不可用 |
| `8` | 长任务失败或超时 |
| `10` | 未分类内部错误 |

### 6.2 输入约束

- JSON 请求支持 `--input request.json` 和 `--stdin`。
- 页面源码支持独立的 `--file page.vue`，不作为命令行长字符串传入。
- 二进制只通过文件上传。
- `--stdin` 和 `--file/--input` 互斥。
- 覆盖本地文件默认失败，需要显式 `--overwrite`。
- 密码和 Token 不提供普通命令行参数，避免进入 shell history 和进程列表。

### 6.3 写入并发和幂等

页面源码更新必须提供 `base_version_no` 或等价的 `If-Match`：

```powershell
wp page source push 35 --file page.vue --base-version 7 --idempotency-key task-a-page-35-v8 --json
```

现有普通页面 `PATCH` 可以更新源码，但 `PageUpdateRequest` 没有强制基线版本；现有 visual-edit 接口具备 `base_version_no` 和 `source_hash` 校验。CLI 正式写页面前应新增稳定的乐观锁契约，不能让 Agent 的重试覆盖其它编辑者刚提交的内容。

创建页面、上传资源和创建构建任务同样应支持 `Idempotency-Key`，避免调用方在网络超时后重试产生重复对象。

## 7. 命令能力规划

### 7.1 基础与诊断

| 命令 | 阶段 | 说明 |
| :--- | :---: | :--- |
| `wp version` | MVP | 返回 CLI 版本和契约版本 |
| `wp capabilities` | MVP | 返回服务端版本、功能开关和限制 |
| `wp health` | MVP | 检查 Backend 可达性，不启动服务 |
| `wp profile add/list/show/use/remove` | MVP | 管理本地连接 profile |
| `wp context show` | MVP | 展示已解析的服务器、工作空间和项目 |
| `wp completion` | 后续 | 生成 Shell 补全脚本 |

### 7.2 认证与工作空间

| 命令 | 阶段 | 所需 scope | 说明 |
| :--- | :---: | :--- | :--- |
| `wp auth login` | MVP | 无 | 交互登录并换取/创建受限 Token，具体流程待接口确定 |
| `wp auth whoami` | MVP | 无 | 返回当前用户、Token scopes 和 workspace grants |
| `wp auth logout` | MVP | 无 | 清除本地凭证，可选吊销当前 Token |
| `wp workspace list` | MVP | `workspace:read` | 只列出授权交集 |
| `wp workspace get` | MVP | `workspace:read` | 读取当前工作空间 |
| `wp workspace use` | MVP | 本地操作 | 切换 profile 或默认上下文，不改变服务端授权 |
| `wp token create/list/revoke` | 后续 | owner | 管理自动化 Token |

### 7.3 项目和路由

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp project list/get` | MVP | `project:read` |
| `wp project create/update` | MVP | `project:write` |
| `wp project routes get` | MVP | `project:read` |
| `wp project routes replace` | MVP | `project:write` |
| `wp project build-assets` | MVP | `project:read` |
| `wp project delete` | 后续 | `dangerous:delete` |

`routes replace` 是整树覆盖操作，必须带项目当前路由版本或 ETag；没有并发基线时不应开放给自动化 Agent。

### 7.4 页面与版本

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp page list/get` | MVP | `page:read` |
| `wp page source pull` | MVP | `page:read` |
| `wp page create` | MVP | `page:write` |
| `wp page source push` | MVP | `page:write` |
| `wp page metadata update` | MVP | `page:write` |
| `wp page dependencies` | MVP | `page:read` |
| `wp page components` | MVP | `page:read` |
| `wp page versions list/get` | MVP | `page:read` |
| `wp page snapshot` | MVP | `page:write` |
| `wp page restore` | 后续 | `page:write`，需要显式确认 |
| `wp page copy` | 后续 | `page:write`，只允许同空间 |
| `wp page visual-edit preview/apply` | 后续 | `page:write` |
| `wp page delete` | 后续 | `dangerous:delete` |

`source pull` 默认写入文件并同时返回 `current_version_no` 和源码哈希。`source push` 必须携带其中至少一种并发基线。

### 7.5 代码检查

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp check page` | MVP | `page:read` 或专用 `code:check` |
| `wp check component` | 后续 | `component:read` 或专用 `code:check` |

当前代码检查能力主要由内部 AI 工具调用，需要补充不依赖 AI run/tool token 的确定性公共 API。检查结果至少包括：

- `valid`。
- `errors`、`warnings`。
- Runtime Kit 非版本化或未授权导入。
- 组件依赖和资源引用问题。
- 可选的规范化源码哈希。

### 7.6 资源

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp asset list/get/tags` | MVP | `asset:read` |
| `wp asset content pull` | MVP | `asset:read` |
| `wp asset upload` | MVP | `asset:write` |
| `wp asset content create/push` | MVP | `asset:write` |
| `wp asset metadata update` | MVP | `asset:write` |
| `wp asset download` | MVP | `asset:read` |
| `wp asset references` | 后续 | `asset:read` |
| `wp asset archive/restore/copy` | 后续 | `asset:write` |
| `wp asset import/export` | 后续 | `asset:write` / `asset:read` |
| `wp asset delete` | 后续 | `dangerous:delete` |

CLI 不提供图片生成。调用方生成本地文件后使用 `asset upload`。

### 7.7 组件、主题、样式和字体

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp component list/get/versions/dependencies` | MVP | `component:read` |
| `wp component create/update/publish` | 后续 | `component:write` |
| `wp theme list/get` | MVP | `design-system:read` |
| `wp style list/get` | MVP | `design-system:read` |
| `wp font list/get` | MVP | `design-system:read` |
| `wp theme/style create/update/copy` | 后续 | `design-system:write` |
| `wp component/theme/style delete` | 后续 | `dangerous:delete` |

第一阶段重点是给调用方足够的设计系统上下文，不急于让 Agent 修改共享设计资产。

### 7.8 Runtime Kit

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp runtime-kit list` | MVP | 已认证用户 |
| `wp runtime-kit get` | MVP | 已认证用户 |
| `wp runtime-kit manifest` | MVP | 已认证用户 |
| `wp runtime-kit preview` | 后续 | `preview:run` |

输出必须保留版本化 import path、参数 Schema、previewSchema 和可预览信息，供调用方生成合法源码。

### 7.9 预览、截图和构建

| 命令 | 阶段 | 所需 scope |
| :--- | :---: | :--- |
| `wp preview create` | MVP | `preview:run` |
| `wp screenshot start` | MVP | `preview:run` |
| `wp screenshot status/wait/cancel` | MVP | `preview:run` |
| `wp screenshot download` | MVP | `page:read` |
| `wp screenshot batch-start/batch-download` | 后续 | `preview:run` |
| `wp build assets` | MVP | `project:read` |
| `wp build start/status/wait` | MVP | `build:run` |
| `wp build download` | MVP | `build:run` |
| `wp build artifact delete` | 后续 | `dangerous:delete` |

CLI 可以在命令表面提供统一的 `wait` 体验，但 Backend 仍保留截图和构建各自的任务模型。`wait` 应采用带抖动的退避轮询，尊重服务端建议间隔，并在 Ctrl+C 时默认只停止本地等待；只有显式 `--cancel-remote` 才请求取消远程任务。

## 8. Skill 与 CLI 的契约

配套 Skill 不复制完整命令定义，只描述：

- 何时使用 CLI。
- 标准创作闭环。
- 必须先确认工作空间上下文。
- 如何选择组件、资源和 Runtime Kit。
- 如何处理版本冲突、代码检查错误和任务失败。
- 什么时候下载截图并进行视觉复核。
- 哪些危险操作必须停止并请求用户确认。

CLI 自身提供可机器读取的能力目录：

```powershell
wp capabilities --json
wp help --json
wp schema export --output wp-cli.schema.json
```

Skill 声明最低 CLI 和契约版本，例如：

```yaml
cli_name: wp
minimum_cli_version: 0.1.0
api_contract_version: 1
```

## 9. Backend 需要补齐的接口与约束

现有 API 已覆盖大部分读取、资源管理、截图和构建能力，但 CLI MVP 仍需要补齐：

1. PAT 创建、校验、吊销、scope 和 workspace grant。
2. Cookie/Bearer 最终统一为同一种请求主体上下文。
3. 面向外部调用的 workspace assertion 与对象归属校验。
4. 页面源码更新的强制乐观锁。
5. 项目路由整树覆盖的强制乐观锁。
6. 创建类和长任务接口的幂等键。
7. 不依赖 AI run/tool token 的页面和组件代码检查 API。
8. 资源、截图、构建站点和同类临时资源的统一交付鉴权入口。
9. 稳定的能力发现和 API 契约版本接口。
10. 统一错误字段 `code`、`message`、可选 `data`、request ID，并由 CLI 补充 recoverable/hint 映射。
11. 工作空间角色权限矩阵。

CLI 不应为了赶进度直接调用 `backend/app/ai` 中绑定 run/session 的工具入口。可以复用这些工具背后的确定性 Service，但需要通过普通 API 和普通用户授权上下文调用。

## 10. 测试方案

### 10.1 Backend

- PAT 哈希、过期、吊销和 scope 单元测试。
- Token grant、active membership、成员角色的权限组合测试。
- 两用户、两工作空间的列表隔离测试。
- 使用其它空间的 project/page/asset/component/job ID 访问时的拒绝测试。
- 路径 workspace 与对象真实 workspace 不一致测试。
- 页面版本冲突和幂等重试测试。
- 截图、构建任务和产物下载的工作空间校验测试。
- 资源、截图和构建站点的匿名访问拒绝测试。
- 用户 Cookie、PAT 和 Runtime 短期服务凭证三种交付访问路径测试。

### 10.2 CLI

- profile 和工作空间解析优先级测试。
- profile 工作空间覆盖保护测试。
- stdout 纯 JSON、stderr 日志和退出码测试。
- stdin、源码文件、上传下载和覆盖保护测试。
- HTTP 超时、重试、401/403/404/409/5xx 错误映射测试。
- job wait 的成功、失败、超时和 Ctrl+C 测试。
- Windows PowerShell、bash 的参数兼容测试。
- Token 不进入日志、异常和配置快照的安全测试。

### 10.3 E2E

至少准备两个用户和两个工作空间：

1. 使用 workspace A profile 完成读取、页面创建、源码提交、截图、快照和构建。
2. 使用同一 Token 尝试读取 workspace B 的对象，必须失败。
3. 使用 workspace B profile 验证其正常创作链路。
4. 吊销 Token 后再次调用，必须立即失败。
5. 用户成员关系失效后，未过期 Token 也必须失败。

## 11. 分阶段实施

### 阶段 0：契约确认

- 确认 CLI 包名、命令名和外部 API 版本策略。
- 确认第一版 Token 是否严格单工作空间。
- 盘点所有公开文件交付路由，确认统一 `DeliveryAccessContext` 覆盖范围。

### 阶段 1：安全基础

- 实现 PAT、workspace grant、scopes 和审计。
- 统一 Cookie/Bearer 请求主体。
- 补充 workspace assertion 和跨空间拒绝测试。
- 增加能力与契约版本接口。
- 为资源、截图、构建站点和同类临时资源接入统一交付鉴权。
- 让 Runtime 构建资源请求携带现有短期服务凭证。

### 阶段 2：只读 CLI

- 实现 profile、auth、context 和标准输出。
- 开放项目、页面、资源、组件、主题、样式、字体和 Runtime Kit 查询。
- 编写第一版 Skill，让 Agent 能正确收集创作上下文。

### 阶段 3：创作闭环

- 页面创建、源码乐观锁更新和代码检查。
- 资源上传和内容写入。
- 截图任务、下载、视觉复核循环。
- 页面快照、项目构建和产物下载。
- 完成双工作空间 E2E。

### 阶段 4：共享资产与高风险能力

- 组件创建和发布。
- 主题、样式修改。
- visual-edit、批量截图和离线包。
- 删除、恢复和跨空间导出/导入。
- 根据真实 Agent 使用记录优化 Skill 和错误恢复提示。

## 12. 验收标准

CLI MVP 达到可用需要同时满足：

- 调用方 Agent 不使用平台 LLM，也能完成页面创作、截图迭代和构建交付。
- 一次创作任务只在一个明确的工作空间内运行。
- 任何仅替换对象 ID、job ID、文件哈希或 workspace 参数的越权尝试都无法读取其它空间内容。
- 页面并发修改不会静默覆盖新版本。
- 网络重试不会重复创建页面、资源或构建任务。
- stdout JSON、错误码和退出码稳定，可被 Skill 和不同桌面 Agent 可靠消费。
- Token 可过期、可吊销，用户失去成员资格后授权立即失效。
- 资源、截图和构建站点拒绝匿名访问，用户访问和 Runtime 内部回源均经过工作空间校验。
