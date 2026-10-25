# CLI 字体管理与主题图片、字体配置实施规划

规划日期：2026-10-20。状态更新（2026-10-25）：WP01–WP08 已完成，WP09 功能验收通过，发布安装包对账待做；真实证据见[验收记录](live-validation-2026-10-20.md)。早期缺少真实环境证据的“全部完成/生产交付”结论已撤回，[修复记录](../../../archive/developer-work-2026-10/cli-font-theme/review-fixes.md)保留审查过程。

| 仓库 | 分支 | 分支起点与评估基线 | 职责 |
| --- | --- | --- | --- |
| `web-presentation` | `feature/cli-font-theme` | `dev` / `12d2d2564e31c6f5cd7a9c0755c5f8f54a22a5a4` | 公共契约、Backend、生成物、跨仓验收 |
| `web-presentation-cli` | `feature/cli-font-theme` | `master` / `66d793147a968cf8c2ef00f2253cfa8693a9f0d9` | CLI、同步客户端、输出、Skill、分发 |

CLI 评估版本为 `0.3.4`，Skill 为 `1.4.2`。以上 commit 用于追溯分析，不能当作新功能的最低支持版本。发布时另行固定两仓完整 commit、CLI/Skill 版本及 OpenAPI 摘要。

本文件维护平台侧契约候选、实施顺序和联合验收；[工作包清单](work-packages/README.md)记录依赖和进度。[CLI 实施规划](https://github.com/LLMxPM/web-presentation-cli/blob/feature/cli-font-theme/docs/font-theme/implementation-plan.md)维护具体命令与客户端工作包。跨仓 GitHub 链接在对应分支推送后可用；本地 CLI 文档位于同级 `web-presentation-cli/docs/font-theme/`。已交付契约仍以 [External API v1](../../reference/external-agent-api.md)为准，下文目标契约须经 WP01 冻结后实施。

## 1. 交付目标与范围

用户可以通过 CLI 完成：上传字体文件 → 注册字体 face 并归入字体族 → 创建或修改主题的图片与字体配置 → 应用到项目 → 查询结果与预览验证。

本期范围：

- 字体注册项的列表、详情、注册、配置更新及移动到其他字体族；字体族的列表、详情和重命名。
- 主题默认 Logo、反色 Logo、项目图标的绑定、更换与清空。
- 标题、正文、代码三个字体槽位的字体族绑定、内置预设切换和恢复默认。
- 字体文件复用现有资源上传、下载与带 `expected_file_hash` 的替换接口；共享主题变更后验证新预览与新构建。
- 补齐权限、幂等、字段省略/显式 null、引用状态与跨仓契约验证。

本期不包含：背景图/封面图等新主题槽位、字体转码/子集化/在线字体下载、自动解析字体元数据或文件名、批量上传并自动注册、字体注销/停用/硬删除、MCP 新工具、OAuth、内部内容助手工具扩权。内置助手关于主题 Logo 与字体写入的限制保持原边界；开放 External API 不等于开放内部 AI 工具。

现有模型可承载本期目标，预计无需迁移。WP01 必须复核唯一约束与并发行为；确需迁移时先更新本规划、增加双库迁移验证，再实施。

## 2. 现有基础与差距

| 环节 | 已核对事实 | 需要补齐 |
| --- | --- | --- |
| 文件资源 | CLI `asset` 已接受 font，Backend 支持 woff2/woff/ttf/otf | 上传文件不等于注册字体；流程必须区分成功阶段 |
| 注册项 | `WorkspaceFontService` 已维护格式、字重、样式、显示策略和所属族 | External 只有列表；现有写方法自行 commit，不能直接套入幂等事务 |
| 字体族 | 内部已有族列表、重命名、同名合并与 face 归属调整 | External 缺少族查询与重命名，主题绑定所需 family_id 不易发现 |
| 主题读取/更新 | 公共响应含图片、字体字段；External PATCH 已复用完整内部更新 DTO | CLI 帮助/Skill 仍只说明名称、描述、色板；普通详情展示不全 |
| 主题创建 | 内部创建支持完整设计字段 | External 创建 DTO `extra=forbid`，仅允许 key/name/description/palette，且路由只转交这些字段 |
| 运行链路 | 已有字体 Bundle、字体注册、ThemeLogo、资源依赖和构建收集 | 需验证配置修改后的身份失效、资源收集、截图与独立构建结果 |

关键源码：[主题 DTO](../../../../backend/app/schemas/theme.py)、[字体 DTO](../../../../backend/app/schemas/font.py)、[External 目录](../../../../backend/app/api/routes/external/catalog.py)、[主题路由](../../../../backend/app/api/routes/external/themes.py)、[字体服务](../../../../backend/app/services/workspace_font_service.py)、[主题服务](../../../../backend/app/services/workspace_theme_service.py)。

### 必须先修复的现有问题

1. `_resolve_theme_payload` 清空图片 ID 时仍回退旧 `logo_path` / `invert_logo_path` / `project_icon_name`，配置组装又使用该回退值。必须在显式清空时同步清空名称，并保留未提交字段与历史路径兼容。
2. External 主题 PATCH 的幂等指纹使用完整 `model_dump()`，丢失字段是否提交的信息。“省略”和“显式 null”可能形成相同指纹，但产生不同业务效果。必须保留字段存在性，覆盖同键异输入冲突。
3. 现有主题/字体引用读取检查归属和类型，但不能据此假定归档资源、历史副本及无启用 face 的字体族都已被排除。新增绑定与注册需明确拒绝条件；现有失效引用的读取与修复路径不能被一起封死。

## 3. WP01 待冻结的公共契约

以下为目标候选，不是当前可调用接口清单。所有路径均位于 `/api/v1`，对象归属由 `X-Workspace-ID` 与当前凭证权限共同校验。

| 接口候选 | 用途 | Scope 候选 | 写入要求 |
| --- | --- | --- | --- |
| `GET /fonts` | 保持现有分页字体列表 | `asset:read` | 保持已有默认行为和响应兼容 |
| `GET /fonts/{font_id}` | 查询单个 face | `asset:read` | 只读 |
| `POST /fonts` | 对已有字体资源注册 face | `asset:write` | Idempotency-Key；不隐式上传文件 |
| `PATCH /fonts/{font_id}` | 更新配置或调整 family_name | `asset:write` | Idempotency-Key；省略字段保持原值 |
| `GET /font-families` | 分页查询字体族及 face | `asset:read` | 只读 |
| `GET /font-families/{family_id}` | 查询字体族详情 | `asset:read` | 只读 |
| `PATCH /font-families/{family_id}` | 重命名字体族 | `asset:write` | Idempotency-Key；同步主题字体标签 |
| `POST /themes` | 创建含图片、字体配置的主题 | `design-system:write` | Idempotency-Key；保留默认色板行为 |
| `PATCH /themes/{theme_id}` | 更新或清空主题配置 | `design-system:write` | Idempotency-Key；保持 key 不可变 |
| `GET /workspaces/{id}/capabilities` | 披露操作与字体预设 | 沿用当前能力查询鉴权 | operations 从注册表派生；新增 fonts.presets 候选字段 |

### 对象、字段和错误语义

- `asset_id` 是字体文件资源，`font_id` 是注册项，`family_id` 是字体族；主题 `*_font_family_id` 只接受族 ID。同一资源只注册一次，同族同字重/样式的重复 face 返回稳定冲突。
- 注册使用 `asset_id`、`family_name`、可选 `font_format`、`font_weight`、`font_style`、`font_display`；family 不存在时按现有服务规则创建，注册项默认为 active。更新不开放 asset_id 和 status，只更新上述配置与归属。外部写 DTO 拒绝未知字段及不具备清空语义的显式 null，避免直接暴露内部模型的停用能力。
- 图片字段为 `logo_asset_id`、`invert_logo_asset_id`、`project_icon_asset_id`。Logo 允许 image/icon，项目图标只允许 icon；写入使用真实资源 ID，不能传路径、URL 或 base64。
- 字体槽位为 heading/body/code，每槽包含互斥的 `*_font_family_id` 与 `*_font_preset`。标题/正文预设为 platform-sans、system-ui，代码为 platform-mono、monospace；从 `platform_fonts.py` 派生 Schema/能力数据，CLI 不维护另一套允许值。
- PATCH 未提交字段保持原值；图片 ID 显式 null 清空 ID 与名称。选择非空 preset 自动解除该槽旧 family 绑定；选择非空 family 切换为该族。恢复平台默认的统一载荷为该槽 family_id 与 preset 同时传 null。WP01 补全单独 null、混合字段和非法双来源的真值表，防止改变现有内部接口的合法输入。
- 色板继续使用完整 `ThemePalette`；不新增任意 YAML/CSS 字体或颜色写入口。创建色板省略时仍使用 External 既有默认值，不在本期顺带更换默认视觉。
- 候选 HTTP 语义：401 身份失效，403 Scope/空间授权不足，404 当前空间目标不存在，400 资源类型/状态/字段取值不合法，409 重复注册/族名冲突/同键异载荷，422 请求 Schema 不合法。WP01 复用现有错误码并冻结新增码，记录现有路由的空间隐藏语义，不扩大跨空间信息暴露。
- 新增写操作的业务结果与幂等记录同事务提交；同键同输入返回首次结果，异输入冲突。先证明回滚与并发冲突可恢复，再开放操作。已有主题更新指纹变更需明确存量幂等记录的兼容边界，不得静默重执行旧请求。
- 响应沿用已注册字体与族摘要，供客户端取得真实 ID。字体文件下载使用 External 资源文件接口，不能把内部 `asset_url` 当作 PAT 下载入口。

## 4. 工作包与里程碑

详细卡片见[执行清单](work-packages/README.md)。本期共 9 包，每包包含范围、前置、验收和证据回填。

| 编号 | 工作包 | 主责仓库 | 前置 |
| --- | --- | --- | --- |
| WP01 | 契约、共享样例与兼容边界冻结 | 主仓 | 无 |
| WP02 | 主题清空、字段存在性与引用校验 | 主仓 | WP01 |
| WP03 | 字体服务事务边界与查询能力 | 主仓 | WP01 |
| WP04 | 字体 External API、权限与能力发现 | 主仓 | WP01、WP03 |
| WP05 | 主题 External 创建/更新一致性 | 主仓 | WP01、WP02 |
| WP06 | CLI 字体与字体族命令 | CLI | WP01、WP04 |
| WP07 | CLI 主题配置与可读输出 | CLI | WP01、WP05 |
| WP08 | Skill、安装包与兼容版本 | CLI | WP06、WP07 |
| WP09 | 联合验收、文档与交付记录 | 主仓牵头、两仓参与 | WP02–WP08 |

- M0：WP01 完成，公共字段/路径/权限/错误/真值表可作为唯一实现输入。
- M1：WP02–WP05 完成，Backend 可联调，OpenAPI/生成物/权限/幂等检查通过；CLI 尚未交付时不能宣称 CLI 已支持。
- M2：WP06–WP08 完成，CLI 命令与打包可验收；WP09 完成后才能声明端到端交付。

依赖主链：`WP01 → (WP02 → WP05 → WP07；WP03 → WP04 → WP06) → WP08 → WP09`。实现分工可沿两条链推进；共享 DTO、operation 注册表、capabilities 和生成物的合入顺序需协调，避免互相覆盖。本规划不自动创建并行任务。

## 5. 验证与交付门槛

测试选择、服务探测和 E2E 数据纪律遵循 [`dev-start-test`](../../../../.agents/skills/dev-start-test/SKILL.md)及其[测试矩阵](../../../../.agents/skills/dev-start-test/references/testing-matrix.md)。下表定义本功能证据，不另建服务启动流程。

| 层级 | 必须覆盖的证据 |
| --- | --- |
| 领域服务 | 同资源重复注册、同族同 weight/style、可变字重、归属移动、族名唯一、主题标签同步、拒绝失效资源、失败回滚 |
| 主题语义 | 每个图片/字体槽的省略、null、替换、恢复默认、互斥来源；名称回退清理；复制仍保留有效绑定 |
| External | Scope、空间隔离、真实 ID 类型、同键重放/异载荷冲突/并发、拒绝未知字段、非法 null/格式/预设；现有 PAT/主题 key 约束回归 |
| 契约生成 | HTTP DTO 改动后运行 codegen:editor-api 和 test:contracts:generated；联动 CLI 全部注册命令与真实 Backend OpenAPI 对拍 |
| CLI/Skill | 命令输入、JSON/raw/表格、错误退出码、预设动态发现、严格帮助与 Doctor、安装包与 Skill 资源校验 |
| 跨模块 | 预览字体 Bundle 包含同族启用 face，图片与字体更新使新预览身份/截图检查失效；独立构建含正确资产与当前配置，旧构建保持当次快照 |
| 联合实测 | 真实 CLI 上传 Regular/Bold → 注册同族 → 创建含两种 Logo/项目图标的主题 → 项目应用 → 真实字体加载与 PNG → 修改/替换/清空/默认恢复 → 新构建检查 |

主仓基线回归包含现有 `test_workspace_fonts.py`、`test_workspace_themes.py`、`test_external_api_v1.py`、`test_external_asset_replace.py`；新增字体 External 与主题配置定向测试。External 契约变更补 Gateway/CLI Skill 契约检查。若修改 Runtime，按实际范围增加对应字体/主题单测和真实渲染检查。

事务与唯一性新增断言在 SQLite 和 PostgreSQL 分别验证；PG 环境缺失时明确记为未验证，不能以 SQLite 通过代替。跨仓 OpenAPI 因相邻仓缺失而 skip 不等于通过。CLI 无构建触发命令时，独立构建验证由平台现有构建入口执行，不能让 CLI 越过公开 API 调用 Runtime。

WP09 回填两仓 commit、版本/OpenAPI 摘要、测试命令与结果、skip/未运行项、临时账号/空间标识、Mutation/Renderer attempt、截图与构建证据。证据不含凭证、私有存储键或长期访问 URL；大文件与可再生产物不提交。

## 6. 文档、发布与后续

- 公共契约正文由主仓 `docs/developer/reference/external-agent-api.md` 维护；CLI 命令与 Skill 正文仅在 CLI 仓维护。主仓 `cli.md` 保留边界与入口，避免复制命令清单。
- 开发导航本轮只增加“待实施”入口；功能验收后再同步用户流程、CLI 能力矩阵、README、Skill 版本及兼容范围。无需因本次计划修改 AGENTS.md。
- 交付顺序为平台契约/实现 → CLI 消费/打包 → 联合验收 → 版本发布；新命令遇旧 Backend 时给出明确的不支持错误，帮助/Doctor 继续遵守严格 OpenAPI 失败语义，不使用离线 Schema 或内部路由兜底。
- 本轮不提交、推送、打标签、发布安装包或部署服务。后续发布前记录兼容平台版本与 CLI/Skill 支持范围，不把评估基线写成支持版本。
- 后续候选另立工作包：自动字体元数据解析、一次上传并注册及失败恢复、注销/停用的引用保护、字体族合并、字体子集化、新主题图片槽位。它们不是 WP09 的完成条件。

## 7. 实施历史与验收边界

- **状态**：已有实现与历史提交如下，WP09 仍待 PostgreSQL、真实 CLI/字体加载、截图和独立构建验收。
- **主仓 Git 提交**：
  - `31c2a80` docs: 建立 CLI 字体与主题配置实施规划与工作包
  - `89c31de` docs(contract): 冻结字体与主题配置公共契约及共享样例 (WP01)
  - `319fd69` feat(theme): 实现主题图片清空语义、真值表解析与引用校验 (WP02)
  - `32d51fc` feat(font): 完善字体服务事务控制、单项查询与纯函数模块抽取 (WP03)
  - `56eb28e` feat(font): 提供字体与字体族 External API v1 及能力发现 (WP04)
  - `3636d92` feat(theme): 统一主题 External 创建与更新配置、真值表与幂等指纹 (WP05)
- **CLI 仓 Git 提交**：
  - `23ccbbc` docs: 建立 CLI 字体与主题配置实施规划与工作包
  - `2fac29a` feat(font): 实现 CLI 字体与字体族管理命令及 OpenAPI 契约绑定 (WP06)
  - `c659767` feat(theme): 增强 CLI 主题详情输出与创建/更新设计字段输入支持 (WP07)
  - `f8af454` feat(skill): 更新字体与主题工作流规范，升级 CLI 与 Skill 分发版本 (WP08)
- **版本与分发包**：
  - CLI 版本：`0.3.5`，Skill 版本：`1.4.3`，兼容范围：`requires_cli = ">=0.3.5,<0.4.0"`
  - `web_presentation_cli-0.3.5-py3-none-any.whl` (140,138 bytes, `BA8DE440A3CEEB8318B31E4ADE20DAAFD243BFDCEFE1AE13D995C817010FE46D`)
  - `web_presentation_cli-0.3.5.tar.gz` (131,384 bytes, `FE425B99204D8A16EF1E2483873AC87BBD2110BAB371A9765D4FD05D13FFEC4A`)
- **测试覆盖与验收**：
  - 主仓后端：43 项字体与主题测试全部通过，前端 codegen 契约生成物完全一致；
  - CLI 客户端：195 项全量测试全部通过（包含真实 Backend OpenAPI 契约对拍）；
  - 安装包分发：wheel 与 sdist 的 manifest 内容哈希及 METADATA 校验全部通过。
- **未完成验收项**：PostgreSQL 事务/唯一性、安装包驱动的真实 CLI 联合流程、真实字体加载/Renderer attempt/PNG、独立构建及旧平台兼容实测。历史的 API/Mock/打包检查不能替代这些证据。
- **交付结论（2026-10-25 更新）**：上述版本、产物摘要和测试数字仅为审查前记录。后续已完成真实 CLI/PG/字体加载/PNG/独立构建，见[真实验收记录](live-validation-2026-10-20.md)；用户确认新 CLI 连接当前旧版 Backend 的兼容实测通过。主仓 `de5337a` 与 CLI 仓 `5b2f007` 已提交修复。发布前仍须以拟发布提交重建安装包、核对摘要并写明支持下界；历史快照的包摘要不能直接用作最终发布证据。
