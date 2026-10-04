# 远程 MCP 首批实施交接

初始核对日期：2026-10-03；后续批次接续至 2026-10-04。本记录冻结主仓 M1 身份、M3 契约发现及 ChatGPT web 首批 OAuth 实现边界。当前协议入口见 [ChatGPT 首批授权](./backend/oauth-chatgpt.md)；M0/M7 真实宿主尚未退出，本文不表示远程 MCP 已可用。

## 1. 核对基线与范围

| 仓库 | 核对基线 | 状态 |
| --- | --- | --- |
| web-presentation | `dcf91cbf7e02f0d14cfbf82f4e0911fdef238443` | External API 仅接受 PAT |
| web-presentation-cli（拆仓前 agent-kit） | `5f9489a` | MCP 为历史骨架，尚无首期 binding 注册表 |

从实际 FastAPI 路由、依赖和当前 OpenAPI 离线核对了 **87 个 HTTP 方法/路径组合**。包括主资源路由、附加读取视图、Mutation 别名路由和批量归档。请求路径、DTO、Scope 与幂等要求继续以主仓代码为准；A1/A4 必须依据完成后的 OpenAPI 对拍，不允许使用本文作为离线请求契约。

首期复用项目/页面/组件/文本资源/主题/样式查询与创作、规范、Runtime Kit、字体、Mutation 查询/取消/重试、组件发布和现有预览/截图。首期排除上传、批量归档、Restore、Build、图片生成和内部 Agent 会话。

### 已定位的响应缺口

| 真实入口 | 当前问题 | M3 修正 |
| --- | --- | --- |
| `GET /api/v1/auth/whoami` | user/token/workspaces 是任意字典 | 明确嵌套 DTO，保留旧 PAT 字段；增加 credential 来源 |
| `GET /api/v1/pages/{page_id}/source` | 成功响应仅声明通用 object | 完整源码、页面 ID/code、version_no 类型化 |
| `GET /api/v1/components/{component_id}/draft` | 通用 object，缺少编辑基线 | 完整 content/preview_schema，加 current_version_no、draft_base_version_no、draft_hash |
| `GET /api/v1/components/{component_id}/dependencies` | 成功响应为 Any | 复用已有 WorkspaceComponentCurrentDependencies |
| `POST /api/v1/assets/{asset_id}/content/preview` | 差异结果是通用 object | asset_id/name、changed、unified_diff 类型化 |
| 六类单项 `POST .../{id}/archive` | 仅声明 dict[str, str] | 复用 MessageResponse，响应 JSON 不变 |
| `GET /api/v1/pages/{page_id}/screenshot` | 200 没有 PNG 契约 | image/png binary、页面 ID/版本响应头；不改变等待行为 |

页面详情、源码、版本列表/版本内容共用 `page.get`；组件详情、草稿、版本列表/版本内容共用 `component.get`。每个视图必须从自己的 HTTP 路由取参数和响应，不能使用 operation 主路径代替。现有项目配置、路由树、预览和 Job 请求/响应已有 DTO，保留原契约。

## 2. M1 身份边界

外部请求主体保存用户、不可变 scopes/空间集合和来源明确的 credential。业务路由只读取公共主体，不持有 PAT ORM 记录。

| 来源 | 审计/兼容信息 | 约束 |
| --- | --- | --- |
| pat | token_id、public_id、name、expires_at | 保留现有 all_workspaces 行为与实时成员资格检查 |
| delegated | public_id、grant_id、client_id、service_id、issuer、audience、expires_at | 固定具体空间集合；不可使用 all_workspaces |

`delegated` 结构只能由完整验证器构造，不能凭 HTTP Header 或调用方声明构造身份。当前 HTTP 按 `wp_pat_` / `wp_dlg_` 单次分派；后者仅在显式启用 OAuth 时经过 issuer、API audience、期限、用户/Grant/客户端/服务/源 access 及实时成员范围验证。MCP access/refresh 和服务凭证不能直接访问业务 API，失败没有第二种规则兜底。

whoami 的 `user`、`token`、`workspaces` 字段保持兼容。PAT 的 token 保留 id/name/token_public_id/scopes/expires_at/all_workspaces；委托身份 token 为 null，credential 明确使用 delegated 及授权/客户端/服务标识，不伪造 PAT ID。credential 只包含公共标识，不包含原始凭证。capabilities.operations 继续为字符串列表，Scope 的 all/any 语义保持现状。

真实委托 HTTP 已验证 whoami、工作空间读取、Scope/capabilities 对等及撤销后拒绝；M4 本地创作/Job/幂等证据见批次 12，真实 PostgreSQL、Gateway 和宿主仍需 M7 验收。

## 3. M3 操作元数据

选择单个版本化扩展 `x-wp-operation`，版本为 1。扩展从真实路由鉴权依赖所持有的 `ExternalOperationSpec` 派生；不得维护另一份 route→scope 映射。

静态操作字段：`version`、`key`、`public`、`required_scopes`、`scope_mode`、`workspace_header_required`、`idempotency_key_required`。workspace_header_required 取实际路由/依赖的 Header 必填约束，不能把注册表中“非豁免”误当成所有详情路由都必须带 Header；实体和 Job 的空间仍由服务端复核。

通用 `/jobs/mutations/{job_id}`、`/cancel`、`/retry` 使用动态结构：`version`、`resolution=mutation_job_type`、`action`、`candidates`、`workspace_header_required=false`、`idempotency_key_required`。candidates 是以 page/component 为键的对象，每项包含 key、required_scopes 和 scope_mode；候选不能合并成同时需要或任一满足的静态权限。执行时只按数据库真实 job_type 决定。

元数据是公开契约，不是用户可用能力。客户端执行前仍使用空间 capabilities，服务端每请求继续鉴权。规范与 capabilities 保持用户相关，不能进入共享公共缓存。旧客户端可以忽略新增扩展；不新增内部 guides 镜像。

## 4. OAuth 选型和未退出项

Authlib 已锁定为 1.8.0，许可证为 BSD-3-Clause。官方提供框架无关授权服务器与 PKCE/刷新/撤销扩展，但授权服务器框架集成主要为 Flask/Django，不能把 FastAPI 客户端集成误认成现成授权服务器。主仓采用每请求独立的同步协议核：异步层预读不可变客户端/凭证快照，Authlib 校验并暂存发行意图，异步层完成 CAS 和事务提交后才交付响应。不会在同步钩子内阻塞异步 Session。[官方授权服务器说明](https://docs.authlib.org/en/stable/oauth2/authorization-server/)、[发布记录](https://github.com/authlib/authlib/releases)、[许可源码](https://github.com/authlib/authlib/blob/v1.8.0/LICENSE)。

M2 开工前需完成适配验证：框架无关协议核接入 FastAPI、平台用户/登录、SQLAlchemy 持久化、PKCE S256、resource 绑定、刷新轮换/重放、撤销、自省与受控 RFC 8693 交换。异步事务和 CAS 应由主仓数据库适配层处理；无内置支持的扩展不能算库已实现。验证失败应重新选型，不能手写整套协议弥补。

| 未冻结/未验收项 | 影响的工作包 | 下一步证据 |
| --- | --- | --- |
| 最小适配验证的登录/真实进程部分 | M0/M2 | 协议、SQLite 并发、自省/撤销/交换核心已验证；仍需平台确认与 PG/真实进程 |
| 首批真实宿主名称、版本和注册机制 | M0/M2/M7 | 与 A0 联合验证；SDK 测试不替代宿主 |
| 公网 origin/issuer/resource/API audience | M2/M6 | 明确配置及启动校验，不能从 Host 推导 |
| opaque 自省 DTO/期限的跨仓消费与清理执行 | M2/A3 | 主仓 DTO/期限及服务运维/有界清理已实现；A3 消费、注册宿主及 PG/部署清理待验收 |
| 全部 MCP binding 与请求/响应对拍 | M3/A1/A4 | MCP 仓库建立首期 binding 后验收 |
| PAT/委托业务对等、轮换后幂等、撤销 | M1/M4 | SQLite HTTP 已覆盖；接续 PG/两个 Backend 与 A5 实机对拍 |
| 真实宿主截图预算与 PNG 链路 | M5/M7 | 宿主时限、实际耗时和真实产物 |

已接受的持久 Job 不因 MCP 断连、Token 到期或撤销自动取消。查询、取消和 retry 仍需当前权限；重放维持 user/workspace/operation/key 边界。主仓本批不修改内部助手与领域队列，不启动或发布 MCP 服务。

## 5. 分步实施证据

### 批次 14：M6 主仓请求与已提交审计关联

复用既有 request ID 上下文，补齐 OAuth 审计提交、协议处理和 External 路由结果三类结构化事件。只从已验证主体、实际鉴权规格和有界 Mutation DTO 记录固定公共身份/operation/Job 字段；区分已验证的 Header 空间上下文与真实目标空间，不采信伪造来源或未验证空间。审计快照在提交前提取、成功提交后输出，日志设施故障不回滚或重试已提交结果。

本批新增 HTTP/隔离数据库与上限/白名单场景 **15 项通过、12 项 PG 因缺专用库跳过**，覆盖真实批准/拒绝→授权码→交换→业务公共身份对拍、并发两用户、Job 重放与 PAT、Scope/结构/空间拒绝、协议错误、提交失败、Handler 故障、ORM 提交过期和服务运维幂等事件。HTTP request ID 使用生产上下文函数绑定，未启动真实 Gateway。相邻 OAuth/委托/M4/存储/确认/服务运维/日志与数据库适配门禁 **133 项通过、111 项 PG 跳过**；另行 CLI/预览/单项归档回归 **24 项通过、15 项 PG 跳过**，两组包含重叠单项归档场景，不合并为唯一场景总数。

OpenAPI 生成物对拍保持 **256 paths/354 schemas**，无 HTTP DTO 或数据库迁移变化；根仓契约 **44 项**、仓库文档/边界 **16 项**、相关 Python Ruff 和 diff 检查通过。完整字段与缺失条件见 [请求关联日志](./backend/external-observability.md)。批次 13 已提交为 `a01ccd1`。

本批未执行真实 PostgreSQL、两个 Backend 进程、MCP 侧 trace 或 Gateway Header/日志穿透，未启动开发服务、推送或部署。Docker 引擎仍不具备此前真实 Nginx 回归所需环境；公网预览、真实 PNG 与宿主预算继续待办。M6 只登记 Backend 实现范围，完整跨服务和发布退出项保持未勾选。

### 批次 13：M5 预览截止时间与委托媒体契约

External 项目/页面 preview-artifact 成功响应增加必填 UTC ISO 8601 `expires_at`，继承统一 artifact 字段，不复制响应模型。真实 `PreviewService` 在写入后读取 artifact 元数据，票据和响应采用缓存截止/原有一小时票据上限的较早值；秒级 `exp` 与 `expires_at` 相同。元数据缺失/到期返回 410，损坏返回 503，不回退猜测 TTL。内部统一 DTO 增加可空字段，组件/资产等其余生产者继续兼容，不声明它们已具备期限。

新增真实授权码→服务交换→预览构建的 ASGI 场景 **8 项通过、8 项 PG 因缺专用库跳过**，覆盖项目/页面、60 秒及 7200 秒缓存 TTL、票据/缓存/响应期限对拍、缺 preview:run、跨用户空间拒绝以及缺失/到期/损坏元数据。使用专属 SQLite、独立 memory 运行态及仅存进程的测试 RSA 钥；没有替换预览构建或身份验证。双入口矩阵明确登记 External 必填期限差异，并约束其余字段一致。

相邻预览、密钥环、清理、可视编辑、运行态容量、组件预览、External API/OpenAPI、双入口与数据库适配门禁 **99 项通过**；扩充夹具后的 M4 重放/权限/归档专题 **27 项通过、27 项 PG 跳过**。API codegen 与生成物对拍通过（**256 paths/354 schemas**），Editor 类型检查、根仓契约 **44 项**、相关 Python Ruff 与 diff 检查通过。无数据库迁移要求。批次 12 已提交为 `04926b6`。

已携当前生成文档执行真实 Nginx 命令，Docker Linux 引擎管道不存在，专属网络/容器未创建。默认 Backend/Runtime/Renderer/Editor 端口未发现监听，未重复启动服务或改开发数据；本批未执行公网预览、真实 Renderer/Runtime PNG、冷/热/繁忙/并发耗时或 ChatGPT 宿主预算测试。M5 实机退出项继续未勾选，接续专属测试拓扑与跨仓 A6/M7 验收。

### 批次 12：M4 委托创作、Job 权限与幂等修复

复用既有页面/组件 Mutation 队列和身份依赖，未增加 MCP Worker 或内部 ExternalBatch。九个重任务入口及别名通过真实授权码 HTTP 兑换、服务交换和 External Bearer 提交；原键在重新交换、刷新和同用户 PAT 后仍只受理一个 Job。另覆盖同键异载荷、两个请求竞争、两用户两空间交错调用、动态 Job 读写权限及伪造 resource_type/空间 Header、人工 retry 新 ID 和原基线保留、failed 查询 HTTP 200。

修复两类重放缺口：组件 edits/重元数据省略的版本/hash 沿用首次 Job，不随当前草稿漂移，保留各路由历史指纹顺序和幂等命名空间；页面软删除、组件归档后原有效 key 可恢复原成功响应，仍复核当前身份/空间权限，新 key 和普通详情读取继续返回 404。页面/组件轻元数据、组件发布、单项归档保持同步，发布重放只生成一个正式组件版本。没有 DTO 或数据库迁移变更。

从真实 HTTP 入队和真实租约认领到独立 Session 的领域提交，验证页面版本、组件版本/草稿冲突不覆盖且不可 retry 升级基线；取消先提交则不写实体，完成先提交则取消冲突；凭证到期/Grant 撤销拒绝后续请求且已受理 Job 仍能按领域规则完成。受理响应丢失使用客户端传输故障注入，规划阶段使用受控产物；这些不代表真实网络断连、Renderer 诊断或同时竞争的实机验收。

本批新增 M4 场景 **43 项 SQLite 通过**；连同 OAuth HTTP/真实委托、PAT、External API、主体、幂等、Mutation 与数据库适配门禁集中回归共 **159 项通过、70 项 PG 因缺专用库跳过**。随后补充归档过期键两例，并验证最终归档专题 **5 项通过、5 项 PG 跳过**，覆盖幂等回滚后的 ORM 过期边界。变更的生产/测试 Python Ruff 和 diff 检查通过；生成物对拍保持 **256 paths/353 schemas**；仓库文档/边界 **16 项通过**。operation→存储映射、隐式基线、取消和 retry 说明见 [External Mutation 边界](./backend/external-mutations.md)。

已执行 `pnpm run test:contracts:gateway`，Docker Linux 引擎管道不存在，测试在创建专属网络前失败，未创建演练容器。真实 PostgreSQL、两个 Backend 进程、公开 Gateway、MCP A5/ChatGPT 宿主和 Renderer E2E 未执行；未改开发数据库、未启动开发服务或推送部署。接续 M5 媒体链路与 M7 实机门禁。批次 11 已提交为 `980dfcb`。

### 批次 11：MCP 服务运维与 OAuth 有界清理

新增服务登记/列表/Secret 文件轮换/停用 CLI，以及默认预检的清理 CLI。服务状态变更与固定公共身份审计同事务提交；交换先取得同一服务 UPDATE 围栏再取得 Grant 围栏，停用撤销已有委托，显式换新密钥启用后旧委托不能复活。交换审计保存公共服务 ID，Token 清理后仍可关联服务。

后台 `oauth-cleanup` 每五分钟回收一个批次，关闭 OAuth 后继续运行；按到期/撤销七天及审计三十天进入回收资格，refresh 在家族存活期保留重放证据。Token 来源图按后代优先删除，无级联清理 Grant/注册/Job，积压和引用可能延长实际保留期。迁移 `20261004_0101` 添加可空审计服务 ID 和三个依赖索引；升级/降级、Secret 边界和命令见 [MCP OAuth 维护](../deployment/operations/oauth.md)。

集中回归协议、配置、数据库适配门禁、存储、确认、HTTP、真实委托、服务运维、清理、CLI 和迁移：**186 项通过、104 项 PG 因缺专用库跳过**。覆盖停用与交换的两种提交顺序、停用后重新启用、重复登记竞争、提交故障回滚、活跃家族重放、依赖图清理、批次限制、并发清理和后台失败/取消；使用独立服务/Session 与测试 ASGI，不代表两个真实 Backend 进程。仓库文档/边界 **16 项通过**，API 生成物对拍保持 **256 paths/353 schemas**，新增及变更的 OAuth 模块 Ruff 和 diff 检查通过。`main.py` 全文件 Ruff 的 I001/RUF100 为 HEAD 已有问题，本批未全文件格式化。

真实 PostgreSQL、两个 Backend 进程、Gateway、ChatGPT 宿主和 Renderer E2E 未执行；没有修改开发数据库或启动开发服务。M2 主仓运维实现已完成，下一批接续 M4 委托创作/Job/幂等对拍，PG 与跨仓 Gateway/发布门禁继续待验收。

### 批次 10：真实委托 Bearer 接入 External API

外部 HTTP 依赖按 `wp_pat_` / `wp_dlg_` 单次分派，委托必须完成实时来源链验证；未知类型、MCP access/refresh、重复认证头和 OAuth 关闭均拒绝。重用现有业务路由和 operation 依赖，没有第二套资源路由或 PAT 伪记录。

新增 12 项真实委托 HTTP 用例：Cookie 确认→授权码兑换→服务交换→空间读取闭环，相同用户/空间/Scope 的真实 PAT 与委托 capabilities 完整对拍，Scope 不足/未来空间拒绝，授权/成员/服务/源令牌失效后立即拒绝。集中回归 OAuth 协议/配置/存储/迁移、确认/HTTP、主体/身份、PAT、全部相关 External API 契约：**212 项通过、81 项 PG 因缺专用库跳过**。Ruff、生成物对拍和仓库 16 项检查通过。

下一批仍需服务登记/清理运维入口、委托创作/Job/幂等、公开 Gateway 与真实 ChatGPT 联调。Docker 引擎不可用导致真实 Nginx 命令失败，未创建演练网络/容器；未运行 Renderer E2E，未推送或部署。

### 批次 9：Editor 授权确认与外部授权管理

新增独立 Cookie 登录保护的 `/oauth/consent` 和账户 `/settings/account/grants`。默认只读、写权限显式勾选、具体空间至少一项；过期禁用批准，拒绝不需要范围选择。nonce 不进入路由/本地存储，卸载后迟到响应不导航。账户显示当前可见空间名称与失效提示，整链撤销确认后刷新真实状态。

Editor 完整门禁通过：类型检查、142 个测试文件/791 项测试、生产构建。生成 DTO 对拍通过（256 paths/353 schemas）；账户 HTTP 17 项通过、17 项 PG 跳过，仓库文档/边界 16 项通过。未执行真实 ChatGPT 浏览器登录联调与 Renderer E2E；授权 UI 不代表 MCP 仓库 MCP 服务已交付。

### 批次 8：公开授权、Cookie 确认与授权管理 API

生产装配 OAuth 发现/authorize/token/introspect/revoke 和 Cookie 账户确认/Grant 管理。受限 CIMD 注册不能恢复停用客户端；确认绑定 user/session/nonce，具体空间与权限仅可缩小，CAS 消费及 Grant/Code/审计同事务提交。Gateway 区分协议端点和 Editor 确认 SPA；受控真实 Nginx 回归增加对应断言。

新 HTTP/确认和数据库边界验证：49 项通过、33 项 PG 因未配置专用库跳过；包含真实 Cookie、批准缩权后真实授权码兑换、错误与拒绝 issuer、失效状态、并发确认/首次注册、提交失败回滚、HTTP 服务自省交换。Editor DTO 重新生成至 256 paths/353 schemas，生成物对拍和仓库 16 项检查通过。真实 Nginx 命令已执行，因 Docker Linux 引擎不可用失败；不把静态路由配置或 ASGI 适配测试当作 Gateway/ChatGPT 连接验收。

### 批次 7：冻结 ChatGPT 网页端首批客户端

按用户选择采用 ChatGPT web。2026-10-04 核对官方授权文档并通过 HTTPS 实读稳定 CIMD 文档（HTTP 200）：数组支持 `none` / `private_key_jwt`，旧单值偏好后者，固定稳定回调。新增受限元数据获取/校验、默认关闭的显式配置和 Authlib RFC 9207 扩展，成功及拒绝回调均保留 state 和精确 iss。协议/配置/CIMD 56 项通过。网页端真实账户与生产 MCP 连接仍待验收；公开路由和确认流程接续下一批。

### 批次 1：M0 独立边界核对

提交 `83b09c0`：冻结 M1/M3 首批边界、登记两仓基线与具体缺口。`pnpm run test:repository`：4 个文件、16 项通过。M0 整体仍待授权 PoC 与真实宿主矩阵。

### 批次 2：M1 基础身份解耦

新增不可变 ExternalPrincipal、来源明确的 PAT/委托快照和 PAT 适配器。业务上下文不再持有 PAT ORM；whoami 增加类型化 credential 并保留旧 token 字段，HTTP 仍只接受 PAT。

提交 `385474b`。验证：外部主体/身份专题、PAT API、External API/契约缺口、PAT 服务、幂等与 Mutation 服务共 **73 项通过**；Editor API 重新生成、生成物一致性与类型检查通过；真实 Nginx OpenAPI、上游 503 与 SPA 边界回归通过。委托对等测试只注入已验证主体，真实 Token 验证、audience、撤销与轮换仍待 M2。数据库结构未变，无迁移要求。

### 批次 3：M3 首批契约发现

87 个 External 路由由 ExternalAPIRoute 从真实依赖生成 `x-wp-operation`。缺失或歧义的操作声明在路由装配时失败；多读取视图共享 operation 并保留各自 Schema，动态 Job 声明独立候选。页面源码、组件草稿与基线类型化，组件依赖、资源 diff、单项归档复用已有响应；PNG 声明媒体类型和版本头。认证后的成功响应使用 private, no-store。

验证结果：

- Backend 主体/身份、全部操作/引用、完整源码和 diff 响应对拍、PAT、External API、幂等、Mutation 与相邻仓 CLI Skill 示例：83 项通过；另有路由装配拒绝缺失/歧义/伪造元数据 3 项通过，共 **86 项**。
- `pnpm run test:contracts`：12 个文件、**44 项通过**，包含仓库文档/部署门禁。
- `pnpm run codegen:editor-api`、`pnpm run test:contracts:generated`、`pnpm run test:editor:check`：通过；导出 252 个 paths、345 个 Schema。
- `pnpm run test:contracts:gateway -- --openapi-file editor/src/types/openapi.json`：当前 Backend 完整文档经隔离受控上游与真实 Nginx HTTP 转发后完全一致；上游 503 透传和 Editor SPA 边界通过。容器/网络在结束后清理。

此处 Gateway 证据使用受控静态上游，不代表已部署新 Backend 或通过 OAuth/MCP Gateway。未运行 Renderer/Runtime E2E、真实宿主授权、委托 audience/撤销/轮换和 SQLite/PostgreSQL 授权消费并发；这些分别依赖 M2/M5/M6/M7。MCP 仓库首期 binding 尚未存在，M3 跨仓退出验收仍待 A1/A4。

### 批次 4：M0 Authlib 协议适配

2026-10-04：根 uv workspace 锁定 Authlib 1.8.0。`services/oauth/` 拆分请求、快照、grant 和协议核；协议核没有公开 HTTP 路由，不更改现有 PAT 认证。

`backend/tests/unit/test_oauth_protocol.py` **20 项通过**：公开/机密客户端、显式 S256、精确 redirect/resource、权限扩张拒绝、重复参数拒绝、期限、state 原样回传、刷新子集与轮换意图、原客户端重放识别。Authlib DEBUG 日志使用脱敏 Token repr，原始凭证不进入快照或响应对象 repr。错误 PKCE 不登记消费且随后可以正确兑换。此批验证协议核行为，尚未提供持久化并发证据或真实 FastAPI 授权入口。

### 批次 5：M2 授权存储与原子消费基础

2026-10-04：新增 8 张授权基础表及迁移 `20261004_0100`。异步 Token 服务在发行与撤销共用的 Grant UPDATE 锁内重读状态，再 CAS 消费来源并同事务写入 access/refresh 和审计。公开路由、用户确认与账户 UI 尚未装配，具体边界见[OAuth 授权基础](./backend/oauth-foundation.md)。

验证：OAuth 协议/配置、SQLite 持久化、迁移往返/ORM 对拍、数据库适配门禁、PAT 身份和 External API 共 **86 项通过**；PG 12 项因尚无专用测试连接跳过。仓库文档门禁 **16 项通过**。并发用独立服务对象、Session 和 ASGI app，不代表两个真实 Backend 进程验收。Docker 引擎未就绪，真实 PostgreSQL 尚无通过证据。

授权码竞争仅一次成功；无效 PKCE 不消费；刷新竞争仅一次成功且重放撤销整个 Grant/家族；刷新 Scope 和绝对期限保持收紧；跨用户撤销、用户/客户端停用、退出空间、Scope 缩减、错误 issuer/resource 和提交故障均拒绝发行。原始凭证只存摘要，审计仅公共 ID。凭证/审计清理期已定义上限，但清理任务待接入。

### 批次 6：M2 服务自省、撤销与受控交换

复用 Authlib RFC 7009/7662，自省只允许预注册 MCP 服务，active DTO 为 `wp_version=1`；inactive 不暴露身份。RFC 8693 作为 Authlib 协议核上的受限领域 grant，固定 source/target，拒绝扩权、actor 和 refresh/delegated 转授。交换与撤销共用 Grant 围栏；委托验证器检查源 access 和全部实时授权节点后才构造 ExternalPrincipal。生产 OAuth 路由和 External 委托 Bearer 分派仍未装配。

OAuth 核心（协议/期限、SQLite 原子消费、服务自省/交换、委托来源链、数据库适配门禁）**94 项通过**；联同迁移往返、PAT 身份与 External API 共 **111 项通过**；PG 36 项因缺专用连接跳过。仓库文档 16 项、Python workspace 全成员共装 17 项、生成物一致性、Ruff 与 diff 检查通过。进一步覆盖了跨客户端撤销不泄露存在性、Scope/目标/来源替换、源期限限制、跨 Grant 来源和交换提交故障。真实平台用户确认、两个 Backend 进程及真实宿主都未用这些测试替代。

接续顺序：完成 A0 真实宿主矩阵与平台登录确认 → M2 用户确认/账户 UI、清理和公开配置 → 接入 M1 委托 Bearer 分派 → PG/两个 Backend 实例、M4/M5 与跨仓 Gateway/发布验收。
