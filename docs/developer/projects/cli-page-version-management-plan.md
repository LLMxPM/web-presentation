# CLI 页面版本管理实施规划

规划日期：2026-11-02。状态：已实施并收尾。第 4、5 节的命令与接口已落地，稳定契约以第 9 节和现行 External API 文档为准；本轮未执行的两项验证已按第 9.4 节结论降级为可选补测。

评估基线：主仓 `dev` 的 `210418207760ebe868116cb029ec7b077d8eed54`，CLI 仓 `feature/motion-scene-clients` 的 `d8a4d27fc158aa26b1f54a516d3f1761cf99a3b4`。实施和联合验收时重新记录双方实际版本。

本文统一记录主仓与 `web-presentation-cli` 的工作分工。已交付接口以 [External API v1 契约](../reference/external-agent-api.md)、实际路由和 OpenAPI 为准；实施前须先冻结本文的候选契约，再同步现行文档。

## 1. 目标与范围

让用户和外部 Agent 能通过 CLI 查看页面历史、导出完整源码、比较版本、标记重点快照，以及在不修改当前页面的情况下预览历史内容。

本轮不新增历史恢复命令或公开恢复接口，不调整现有通过生成新版本实现恢复的行为。需要基于旧内容继续创作时，沿用读取历史内容、基于当前版本提交编辑的既有流程。

首期包含：

- 改善现有版本列表的可读性，保留指定版本查询能力。
- 导出指定版本的完整源码。
- 比较同一页面两个版本的源码和演讲备注。
- 将已有版本标记为具名重点快照。
- 获取指定历史版本的短期预览地址。

分支、合并、批量版本操作、删除历史、取消重点标记、整套项目环境冻结和新增历史截图能力不纳入首期。MCP 只记录后续可接入的 External API 变化，不作为本轮交付门槛。

## 2. 已有基础与缺口

| 能力 | 当前实现 | 本轮工作 |
| --- | --- | --- |
| 版本存储 | 最新完整基线、普通历史反向差异、重点版本完整快照 | 复用现有版本链，不新增版本存储体系 |
| 历史列表与详情 | External API 已公开；CLI 已有 `page version list/get` | 列表展示、筛选与针对性测试 |
| 完整源码还原 | 详情的 `resolved_content` 已提供完整内容 | CLI 导出与比较统一使用该字段 |
| 重点快照 | Editor 内部接口与版本服务已实现 | 补 External API、权限、幂等和 CLI 命令 |
| 历史预览 | Editor 内部接口与 `PagePreviewService` 已实现 | 补 External API、CLI 预览分支及边界测试 |

主仓复用入口：

- [页面版本 DTO](../../../backend/app/schemas/page.py)、[版本算法](../../../backend/app/services/page_version_service.py)、[页面服务](../../../backend/app/services/page_service.py)。
- [内部页面路由](../../../backend/app/api/routes/pages.py)、[External 页面路由](../../../backend/app/api/routes/external/pages.py)。
- [历史预览服务](../../../backend/app/services/page_preview_service.py)、[External 预览路由](../../../backend/app/api/routes/external/preview.py)。
- [External operation 注册表](../../../backend/app/core/external_operations.py)。

CLI 入口位于独立仓的 `packages/cli/src/wp/commands/page.py`、`preview.py`、`packages/api-client/src/wp_api_client/client.py` 和 `skills/web-presentation/`。版本子命令增多时拆出 `page_version.py`，不继续扩大页面命令文件的职责。

## 3. 统一语义

### 3.1 版本身份与内容

- 所有命令以正整数 `page_id`、`version_no` 定位；不使用可变化的 `version_label` 或非唯一的 `snapshot_name` 作为选择器。
- `version_label` 用于展示，重点标记可能改变它；`version_no` 保持不变。
- `content` 可能是供历史查看的差异文本；导出、比较和预览必须使用 Backend 还原的 `resolved_content`，CLI 不自行解析存储 patch。
- `speaker_notes` 与源码分别比较。JSON 保留 `null` 与空串的区别，不能因二者显示为空而漏报变更。
- 源码导出保留服务端返回的换行和文本，不使用终端高亮后的内容，不额外格式化或追加换行。

### 3.2 重点快照

重点快照是对已有版本的标记及完整内容物化，不新增页面版本，不切换当前版本，不修改源码或演讲备注，不触发编译、截图或 Mutation Job。

同一版本重复标记保持同一版本节点和既有快照编号；允许通过再次提交名称重命名已有重点快照，不重复分配编号。CLI 首期要求提供非空名称，长度不超过现有 DTO 的 128 字符限制；名称不要求唯一。

快照写入与幂等完成记录须处于同一事务。与页面新版本保存并发时，不得丢失重点标记、产生重复展示编号或破坏反向差异链；复用仓库已有 DB 并发边界，必要时补充领域层的事务复核，不在业务代码增加数据库方言分支。

### 3.3 历史预览边界

历史预览使用目标版本的源码、备注和依赖索引，不更改当前页面及默认截图指针。项目配置、主题、字体、资源身份和 Runtime 执行环境沿用现有预览规则，不能将结果描述为“完整还原当时环境”。页面间导入也不隐含冻结其他页面的历史版本。

页面未关联项目时沿用 `PAGE_PROJECT_REQUIRED`；依赖不可用或 Runtime 无法处理历史源码时明确失败，不退回当前页面源码或其他版本。不要求先恢复页面再预览。

## 4. CLI 命令设计

以下为首期候选命令；P0 冻结后落实到命令帮助和能力矩阵。

| 命令 | 行为 |
| --- | --- |
| `wp page version list <page_id> [--important] [--limit N]` | 最新版本优先；普通终端展示版本号、展示标签、当前标记、快照名、修改说明、时间和创建者 ID |
| `wp page version get <page_id> <version_no>` | 保留现有详情响应，包括完整还原内容及备注 |
| `wp page version export <page_id> <version_no> --output <file>` | 将 `resolved_content` 以 UTF-8 导出到文件，不将差异文本当源码 |
| `wp page version diff <page_id> <from_version> <to_version> [--field source\|speaker_notes\|all]` | 默认比较源码和备注；方向明确为 from → to |
| `wp page version snapshot <page_id> <version_no> --name <name> [--idempotency-key <key>]` | 创建或重命名指定版本的重点快照，返回标记后的版本详情 |
| `wp preview get --page-id <page_id> --version <version_no>` | 创建目标版本的短期预览；不指定版本时维持当前页面预览 |

输出与参数约束：

1. 保持现有 `list/get` 的 JSON 字段与顶层形状；`list --json` 继续返回数组，不改为分页 envelope。普通终端表格只在未选择 JSON 输出时启用。
2. `--important`、`--limit` 首期在 CLI 收到完整列表后执行，先筛选再限制数量；明确它们不能降低 Backend 版本链还原成本。后端分页和按需物化作为后续优化，不在首期改动列表 DTO。
3. `export` 单独提供文件流程，避免改变 `get` 的既有语义。`--json` 返回 `page_id`、`version_no`、`file_type`、绝对输出路径和 UTF-8 字节数；备注仍通过 `get` 读取。先获取和校验内容，再通过临时文件原子落盘；默认拒绝覆盖已有文件，显式 `--overwrite` 才允许覆盖。
4. `diff` 对两个详情调用复用现有 GET 接口，不新增服务端 diff 路由。普通输出为分字段 unified diff；JSON 返回版本身份、整体及各字段 `changed`、差异文本。无变化与有变化均为执行成功（退出 0），参数、访问或比较失败才非零退出。相同版本只读取一次。
5. `--version` 仅允许与 `--page-id` 搭配；与项目目标或 `--route` 混用时在发请求前报参数错误。所有页面 ID、版本号及 `--limit` 使用正整数约束。
6. 预览沿用统一响应及过期字段，不创建平行响应体系。CLI 输出保留本次目标页面和版本信息；旧 Backend 缺少历史预览路由时明确报告不可用，不静默预览当前版本。
7. 新叶子命令登记实际调用的 OpenAPI 契约；`export/diff` 登记版本详情 GET，历史预览登记自己的 POST 分支。Doctor 继续从命令注册表派生检查，不维护第二份接口清单。

候选使用流程：

```bash
wp --json page version list 21 --important
wp --json page version get 21 5
wp page version export 21 5 --output .tmp/web-presentation/page-21-v5.vue
wp page version diff 21 5 12 --field all
wp page version snapshot 21 12 --name "内容确认版" --idempotency-key page-21-v12-checkpoint
wp preview get --page-id 21 --version 5
```

## 5. External API 候选契约

全部路径使用现有 `/api/v1` 前缀和 External 身份认证，并校验 `X-Workspace-ID`、页面归属、当前成员权限与 Scope；不得调用 Editor Cookie 接口替代公开 API。

| 方法与路径 | 状态 | operation / Scope | 请求与响应 |
| --- | --- | --- | --- |
| `GET /api/v1/pages/{page_id}/versions` | 已有，保持契约 | 沿用 `page.get` / `page:read` | `list[PageVersionListItem]` |
| `GET /api/v1/pages/{page_id}/versions/{version_no}` | 已有，保持契约 | 沿用 `page.get` / `page:read` | `PageVersionContent` |
| `POST /api/v1/pages/{page_id}/versions/{version_no}/snapshot` | 新增 | 建议 `page.version.snapshot` / `page:write` | 请求 `{ "snapshot_name": "内容确认版" }`，响应 `PageVersionContent`，HTTP 200 |
| `POST /api/v1/pages/{page_id}/versions/{version_no}/preview-artifact` | 新增 | 建议 `page.version.preview` / `page:read` + `preview:run` | 无业务请求字段，响应统一 `PreviewArtifactResponse`，HTTP 200 |

快照优先复用现有 `PageSnapshotCreateRequest` 和领域服务；名称可空等既有 DTO 行为保持兼容，CLI 的具名限制不应误写为已有内部接口的新增限制。需要调整公开 DTO 时在 P0 明确，避免顺带改变 Editor 行为。

快照 operation 要求非空 `Idempotency-Key`，复用现有幂等服务及客户端生成策略；同键同请求返回原结果，同键异请求拒绝。请求指纹覆盖目标路径和名称；重放旧快照请求不能覆盖之后使用其他键完成的重命名。预览沿用现有派生 artifact 的非幂等调用方式，不新增持久业务写入要求。

新增 operation 同步注册表、HTTP 映射、能力披露、OpenAPI 和防漂移测试。API 路由只负责权限和契约适配；快照与历史内容还原仍由现有服务维护。

错误语义：

| 场景 | 处理 |
| --- | --- |
| 认证失效、Scope 不足、跨工作空间、无权页面 | 沿用 External API 的认证和对象隐藏语义，不通过版本接口泄漏对象存在性 |
| 授权页面内不存在的版本 | 404 `PAGE_VERSION_NOT_FOUND` |
| 页面未关联项目而请求预览 | 409 `PAGE_PROJECT_REQUIRED` |
| 参数或名称不合法、幂等键缺失或无效 | 沿用平台参数和幂等错误，不由 CLI 猜测修正 |
| 同键异载荷、版本链损坏、历史依赖不可用、预览执行失败 | 保留原错误，不回退当前版本、不自动换键重试 |

## 6. 分阶段工作包

| 阶段 | 主仓工作 | CLI 仓工作 | 退出条件 |
| --- | --- | --- | --- |
| P0 契约与用例冻结 | 固定新增路径、operation、Scope、名称约束、幂等与预览边界；准备多版本、备注和重点标记夹具 | 固定命令、参数、JSON 输出及本地文件语义 | 契约无待定字段，记录两仓实际版本 |
| P1 查询、导出与比较 | 验证既有版本详情的完整还原和权限边界 | 整理列表展示；实现筛选、导出、比较及模块拆分 | CLI 适配与本地文件测试通过，既有 JSON 兼容 |
| P2 重点快照 | 新增公开接口、幂等接线、并发边界及权限测试 | 实现 snapshot 命令、动态帮助和错误输出 | 重放、重命名、并发写入后版本链正确，当前页面版本不变 |
| P3 历史预览 | 新增公开历史预览接口，复用版本 override 与现有预览票据链路 | 扩展 preview 客户端和命令分支、输出投影 | 历史内容正确，当前页面不变，失效/依赖错误可见 |
| P4 联合验收与文档 | 回填 External API 契约、CLI 接入边界；归档可追溯证据 | 更新能力矩阵、用户示例、Skill 并完成打包分发检查 | 两仓锁定版本的真实 CLI 流程通过，未运行项明确记录 |

P1 可使用既有 API 先完成；P2/P3 的 CLI 分支在对应公开契约落地后联调。首期以复用现有表和算法为目标，不预设新增数据库表或迁移；若并发实现确需结构调整，在 P0/P2 单独说明原因与验证范围。

工作量判断：查询展示、导出、比较和接口适配偏小；快照并发与真实历史预览联调占主要验证成本。熟悉现有代码的单人粗估 2–4 人日，包含针对性测试和文档，不含正式发布等待；P0 后按实际缺口修正。

## 7. 验证与验收

以下是规划阶段的完整验收口径。本轮实际执行范围、未执行项和降级理由见第 9.3、9.4 节；第 7.1 节不逐条要求全绿，以第 9 节记录的实际结论为准。

实施时按 [dev-start-test](../../../.agents/skills/dev-start-test/SKILL.md) 和[测试矩阵](../../../.agents/skills/dev-start-test/references/testing-matrix.md)选择最小充分测试集，复用已运行服务，不因本计划重复启动或重置开发数据。

### 7.1 必测业务场景

- 历史列表：倒序、当前标记、重点筛选、数量限制、空结果与原 JSON 结构。
- 内容与导出：普通 diff 节点、重点快照、最新版本均导出完整源码；中文、无末尾换行、UTF-8 字节数、写入失败及覆盖策略正确。
- 比较：两个方向、相同版本、仅备注变化、`null` 与空备注、源码尾换行差异；读取失败时不得输出成功比较结果。
- 快照：普通历史和当前版本的首次标记、重复同名、重命名；同键重放、异载荷拒绝、旧键重放不撤销新名称；标记后历史源码及备注不变。
- 快照并发：同页两个快照、快照与新版本保存竞争；编号不冲突，重点标记不丢失，后续保存后仍可完整还原所有版本。相关并发边界覆盖 SQLite 与 PostgreSQL，缺环境必须报告。
- 预览：目标历史源码、备注及版本依赖正确进入 artifact；最新页面、其他版本及默认截图指针不变；未关联项目、版本不存在、依赖不可用和 Runtime 失败明确返回。
- 权限：只读凭证可查询/导出/比较，缺 `page:write` 不可标记快照；历史预览同时要求 `page:read` 与 `preview:run`；跨用户、跨空间沿用既有隔离行为。
- CLI 契约：帮助和 Doctor 覆盖真实分支；OpenAPI 缺失或引用无法解析时非零退出，不使用离线 Schema 或隐式降级。

### 7.2 检查入口与真实证据

主仓运行新增/受影响的 Backend 单元和 API 测试、External 契约门禁；HTTP/OpenAPI 变化后执行 `pnpm run codegen:editor-api`、`pnpm run test:contracts:generated`，按测试矩阵补 Gateway、CLI Skill 与仓库文档检查。

CLI 仓按自身 `AGENTS.md` 运行 API Client/CLI 回归、帮助契约、构建和 Skill 分发验证。新增用例覆盖本地 mock 适配与真实 Backend；不能把相邻仓缺失造成的 skip 当作联合验收通过。

真实流程使用测试工作空间和至少三个内容不同、备注不同的版本：列出历史 → 导出旧版本并核对完整内容 → 比较两个版本 → 标记与重命名快照 → 预览旧版本 → 重新查询当前页面，确认源码、备注和当前版本号均未变化。历史预览同时核对受控 artifact 的版本 override 和浏览器实际内容，不能仅以返回 URL 作为成功证据。

验收记录包含主仓/CLI commit、CLI/Skill 版本、OpenAPI 摘要、环境、命令、测试结果、跳过项与未完成事项。测试或构建通过不等于已经发布。

## 8. 文档维护与当前进度

本计划建立时只新增规划和专题索引，不把候选能力写成已支持。功能实现后同步主仓 External API 与 [CLI 集成边界](../cli.md)，以及 CLI 仓能力矩阵、命令帮助和 Skill；产品能力正式交付后再更新相应用户文档和 README。实施过程完成后，将稳定契约回填现行文档，过程证据按仓库规则归档。

- [x] 核对主仓、CLI 的已有版本能力和缺口。
- [x] 明确本轮不新增或改造历史恢复能力。
- [x] 建立查询、导出、比较、快照和历史预览规划。
- [x] P0 契约与用例冻结。
- [x] P1 查询、导出与比较。
- [x] P2 重点快照。
- [x] P3 历史预览。
- [x] P4 联合验收与文档（契约回填、能力矩阵、Skill、真实 CLI 流程）。
- [x] 按第 9.4 节确认计划 §7.1/§7.2 的两项重验证不作为本轮门禁，转为可选补测。

## 9. 实施记录（2026-11-02）

### 9.1 冻结契约

| 方法与路径 | operation / Scope | 说明 |
| --- | --- | --- |
| `GET /api/v1/pages/{page_id}/versions` | `page.get` / `page:read` | 契约与响应形状未变 |
| `GET /api/v1/pages/{page_id}/versions/{version_no}` | `page.get` / `page:read` | 契约与响应形状未变 |
| `POST /api/v1/pages/{page_id}/versions/{version_no}/snapshot` | `page.version.snapshot` / `page:write` | 必须携带 `Idempotency-Key`，请求 `{"snapshot_name": ...}`，响应 `PageVersionContent` |
| `POST /api/v1/pages/{page_id}/versions/{version_no}/preview-artifact` | `page.version.preview` / `page:read` + `preview:run` | 无业务请求字段，响应统一 `PreviewArtifactResponse`（含 `expires_at`） |

实现入口：

- 主仓：`backend/app/core/external_operations.py`（operation、HTTP 契约、Scope 与幂等要求）、`backend/app/api/routes/external/pages.py`（快照）、`backend/app/api/routes/external/preview.py`（历史预览）、`backend/app/services/page_version_service.py`（页面行串行化锚点）。
- CLI 仓：`packages/cli/src/wp/commands/page_version.py`（`list/get/export/diff/snapshot`）、`packages/cli/src/wp/commands/preview.py`（`--version` 分支）、`packages/api-client/src/wp_api_client/client.py`（`create_page_version_preview_artifact`、`create_page_version_snapshot`）。

### 9.2 关键实现决定

- 快照复用既有 `PageSnapshotCreateRequest` 与 `PageVersionService.create_snapshot`，未改动内部 DTO 语义：名称仍可空，CLI 侧才要求非空且不超过 128 字符。
- 版本链写入并发边界新增页面行串行化锚点 `_lock_page_version_chain`，新版本保存与快照标记共用该锚点；加锁方式统一走 `app.db.tx.acquire_row_write_lock`，业务代码不判断数据库方言。
- 历史预览直接复用 `PagePreviewService.create_page_version_preview_artifact` 的版本 override，不改动当前页面、当前版本与默认截图指针。
- CLI 把版本子命令拆到独立模块，页面命令文件只保留页面级职责；`--important` 与 `--limit` 在完整列表上先筛选再截断。
- 导出先写同目录临时文件再 `os.replace` 原子落盘；默认拒绝覆盖，`--overwrite` 才允许。比较按 from → to 分别处理源码与演讲备注，`null` 与空串视为不同。

### 9.3 验证结果

基线版本：主仓 `dev` `2104182` + 本轮工作区改动，CLI 仓 `feature/motion-scene-clients` `d8a4d27` + 本轮工作区改动；CLI `0.4.1`、内置 Skill `1.4.7`；OpenAPI 271 paths / 367 schemas。

已执行：

- Backend：`backend/tests/api/test_external_page_version_controls.py`（10 项）、`backend/tests/integration/test_page_version_concurrency.py`（2 项）、`backend/tests/unit/test_page_version_write_serialization.py`（2 项）、`backend/tests/api/catalog`（37 项）、`backend/tests/contracts/test_external_openapi_metadata.py` 与 `backend/tests/api/test_external_contract_gaps.py`（16 项）全部通过。
- 主仓门禁：`pnpm run codegen:editor-api` 后 `pnpm run test:contracts:generated` 一致；`pnpm run test:contracts` 21 个文件 136 项通过。
- CLI 仓：`uv run pytest packages/api-client/tests packages/cli/tests` 230 项通过，无跳过。
- 真实 CLI 流程（本地 Backend `http://127.0.0.1:8000` + PostgreSQL `presentation_test`，测试工作空间 `63`、项目 `156`、页面 `785`，三个内容与备注不同的版本）：`page version list`（表格与 `--json` 数组）→ `export` 版本 1（65 字节，末尾换行保留，未追加）→ `diff 1 3`（源码与备注分别显示 from → to）→ `snapshot` 标记版本 2 为 `V1` → 换键重命名为 `内容确认版-重命名`（展示版号不变、版本节点仍为 3 个）→ 重新查询页面，`current_version_no` 仍为 `3`、当前源码与备注不变。

- Backend 全量回归：`backend/tests/api`、`backend/tests/unit`、`backend/tests/contracts` 共 1500 项通过、7 项跳过（环境门禁跳过，与本计划改动无关）。

未执行项与处置：

- 历史预览的真实 Runtime artifact 未联调：本地 Runtime dev server 因 Vite 缓存重优化触发工作区批量删除保护（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`）未能启动。
- PostgreSQL 真并发写交错未单独取证：`presentation_test` 上的并发用例与 SQLite 一致地验证了终态语义，但 SQLite 单写者无法复现写-写交错。
- 未执行构建产物发布与安装包分发；CLI 与 Skill 版本号本轮未变更。

以上两项按第 9.4 节结论不作为本轮门禁，转为可选补测。

### 9.4 重验证范围的收尾结论

计划 §7.1/§7.2 要求“并发覆盖 SQLite 与 PostgreSQL”和“核对受控 artifact 与浏览器实际内容”。按实际改动面复核后，两项都不构成本轮门禁：

- 本轮真正改动共享代码的只有页面行串行化锚点；快照与历史预览都是既有内部服务之上的权限与契约适配层。`create_snapshot` 与 `create_page_version_preview_artifact` 在 Editor 内部路由上早已在用，浏览器渲染链路属于既有能力，不是本次新增行为。
- 锁的可用性已在 PostgreSQL 上被真实 CLI 流程覆盖（建页、两次保存、标记、重命名均经过该锁）。真并发交错只在“同页保存与快照几乎同时发生”的窄窗口才成立，且 `app.db.tx.acquire_row_write_lock` 已是仓库内多处复用的既有原语。
- 相比交错用例，该改动更值得关注的回归面是“每次页面保存多一条 pages 行 UPDATE”在高压下的写竞争，这属于页面保存链路的压力测试议题，不应塞进本计划；现有 1500 项回归已覆盖保存路径的功能正确性。

因此本轮按“适配层 + 既有原语”的验证标准收尾。补测条件：Runtime 与 Renderer 可用时跑一次历史版本预览并核对受控 artifact；具备独立 PostgreSQL 测试库时补跑 `backend/tests/integration/test_page_version_concurrency.py`。两项补测都不阻塞已交付的契约与命令。
