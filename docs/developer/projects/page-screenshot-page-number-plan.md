# 页面截图真实页码与路由目录身份收敛规划

规划日期：2026-11-04。状态：WP1–WP4 代码与门禁已落地（含真实截图链证据，2026-11-04），待同批发布；WP5 批量重截属写操作，尚未执行。实施记录见第 8 节。本轮不含 MCP 交付。

基线：主仓 `dev` 的 `cd96e0a`，加上随后提交的身份改动 `6266189`（`runtime_build` 出截图身份、字体按实际引用过滤、检查身份与截图身份拆两套，见第 7 节）。跨仓项需要 `web-presentation-cli` 单独提交与发版。

## 1. 目标与接受面

两个目标彼此独立，必须分别落地、分别验收：

1. 单页预览与截图链路能拿到**真实页码**，不再恒为 0。
2. **路由目录不再参与截图新鲜度判定**：页码、总页数、其他页标题、顺序、可见性变化都不使旧截图过期。

已明确接受的代价（按产品决策写死，不得再当缺陷处理）：

- 重排、新增、删除、隐藏路由后，已存截图与封面/缩略图上的页码、`总页数`、目录类文本保持旧值（假新鲜），批量刷新与列表页判定都不会因此重截。
- 一旦因任何其他真实变化重截，新截图会显示当时正确的页码。
- 今后不得再用截图 hash 断言「截图里的页码一定正确」；需要断言时在捕获侧校验。

不在本轮范围：

- 「指纹重算失败被折算成旧截图」（`read_failed:SLIDESHOW_CONFIG_UNSUPPORTED`）继续按现状处理。
- 不新增放映协议、不改 `CAPTURE_POLICY_VERSION` 语义、不给截图身份重新引入任何路由输入。
- 不改构建产物与发布链路的页码计算。

## 2. 现状与根因（已核实）

| 事实 | 证据 |
| :--- | :--- |
| 截图请求不含路由，也不含页码；`page.capture` 的 `operation_options` 只有 `{"capture": "png"}` | backend/app/services/rendering/domain_facade.py:122 |
| 渲染请求 `input_digest` 由 page_code/version/source/viewport/operation_options/runtime_build/资源身份构成，**不含路由** | backend/app/services/rendering/snapshot_service.py:73 |
| 每次预览/截图都新建一次性 artifact，无内容复用 | backend/app/services/preview_service.py:78 |
| 全量路由随 `config_bundle["routes"]` 进入 artifact，所以 Runtime 总能算出真实总页数 | backend/app/services/project_artifact_builder.py:204 |
| 单页捕获走 module 入口，导航路径是 `/src/views/<code>.vue` | backend/app/services/page_preview_service.py:73、runtime/src/core/router/index.ts:23 |
| `useCurrentPage` 只按 `route.path` 精确匹配目录，module 路径永不命中 → `currentPage` 恒 0；`totalPages` 取全项目最大值，是真实值 | runtime/src/runtime-kit/public/composables/page/useCurrentPage.v1.ts:21 |
| 单页宿主路由 meta 只有 `title`/`speakerNotes`，没有 `pageNumber` | runtime/src/core/router/preview-entry-meta.ts:5 |
| `RouteInfo.component` 目前是占位字符串 `'parent-component'`/`'child-component'`/`'unknown'`，仓内无读取方（已 grep 确认） | runtime/src/core/utils/route-generator.ts:404 |
| 目录进入身份的唯一入口是 `ProjectRenderIdentity.route_catalog` → `build_render_context` 的 `routes` 段 | backend/app/services/code_check_fingerprint.py:90 |
| 现场：697 页中 85 页读 `useCurrentPage`（项目 105/126/127/128/129 各 17 页），读 `useRouteCatalog`/`usePageNavigation` 的为 0 页；85 页**全部**写成 `currentPage.value > 0 ? currentPage.value : <常量>` 硬编码兜底 | 只读扫库统计，脚本已删除 |
| 兜底写法没有任何文档或规范来源，是模型看到 `0 / N` 后自愈产生的；`useCurrentPage.v1` 清单示例直接写 `page.currentPage.value // 3` 且无约束说明 | runtime/src/runtime-kit/manifest/runtime-kit.manifest.json:1726 |

## 3. 方案决策

**页码由 Runtime 单点解析，Backend 不再算第二套。**

- 捕获侧：`RouteInfo.component` 改为携带路由配置里的真实组件路径，`useCurrentPage` 在 `route.path` 匹配失败时按当前 module 入口路径反查同一份目录的 `pageNumber`。放映、预览、截图、诊断共用同一算法与同一份 artifact 路由配置，按构造保证一致，且候选页的计划序号自动生效（override 路由已进 artifact）。
- 身份侧：删掉 Backend 的页码目录投影及其 fixture 对拍半区。既然 Backend 不再需要独立算页码，保留复刻只会制造漂移面，按「确认无用即整链删除」处理。`routes_need_screenshot_identity` 与两个能力集合保留，因为 `page_metadata`（页面自身标题/备注）仍按闭包是否可读路由上下文判定。

否决的备选：Backend 在 artifact manifest 注入 `entry_page.page_number`。它需要新增跨服务字段、触碰构建产物 manifest 形状，并把「Backend 算的号」和「Runtime 放映的号」重新变成两份实现，一致性要靠 fixture 对拍维持，收益不抵成本。

## 4. 工作包与顺序

严格按 WP1 → WP2 → WP3 → WP4 → WP5 执行。WP3 的「禁止烘死兜底」措辞必须在 WP1 合入后才能生效，否则会先让画面出现 `0 / 12`。

### WP1 捕获侧解析真实页码（Runtime）

改动点：

- `runtime/src/core/utils/route-generator.ts:404`、`:425`：`component` 取路由配置里的真实组件路径，不再写占位字符串。实施修正：`RouteConfig.component` 在 `config.ts:505/:521` 已被换成 `createViewModuleLoader(...)` 异步 loader，YAML 原始路径只保存在 `meta.componentPath`（`config.ts:511/:527`），因此 `RouteInfo.component` 取自 `meta.componentPath`；直接取 `parentConfig.component` 会把函数写进 `component?: string`。
- `runtime/src/core/utils/`（或 `page-numbers.ts` 旁）新增纯函数：把 module 入口路径（`src/views/<code>.<ext>`）与路由 `component`（`@/views/<code>.<ext>`）归一后比对，返回 `pageNumber | undefined`。
  - 实施注意：composable 内实际能拿到的是 `route.path = /src/views/<code>.<ext>`（带前导斜杠），归一需覆盖 `@/`、`/`、`src/` 三种前缀形态；路径归一优先复用 `runtime/src/core/shared/runtime-preview.ts` 的 `normalizeViewModulePath` / `toAliasViewPath`，不得新写第三套路径归一实现。
- `runtime/src/runtime-kit/public/composables/page/useCurrentPage.v1.ts:21`：`getPageNumberByPath(route.path) ?? 按 module 入口反查 ?? 0`；`title` 与 `routeInfo` 行为不变。
- 未挂路由、路由被隐藏时仍返回 0，不新增语义、不返回猜测值。

门禁与退出条件：

- `pnpm run test:runtime`（含 `preview-entry-meta.test.ts`、`usePageNavigation.test.ts`、`export-pages.test.ts`、`BrowserPrintService.test.ts`、`PDFExportService.test.ts` 对 `RouteInfo` 的既有断言）全绿；新增用例覆盖 module 入口反查命中、隐藏页返回 0、路径命中优先于反查。
- `pnpm run test:render-e2e`：真实 PNG 截图 smoke 通过。
- 真实截图链证据：已由 `page-screenshot.spec.ts` 的 DOM 断言覆盖（PNG 内文字不可机读，改在捕获宿主的 iframe 上断言页脚文本：同一页面在两种路由顺序下分别为 `2 / 2` 与 `1 / 2`），不再单独安排人工证据对。
- 回滚：Runtime 单文件级改动，revert 即恢复 0 语义。`runtime_build` 已被第 7 节摘出截图身份（`_pixel_compiler_identity`），回滚不会改变任何截图 hash、也不会触发重截；代价是回滚后新截图回到「0 或常量」语义，而存量截图仍显示真实页码，两者不一致只能靠一次性重截纠正，回滚须与发布策略（见 WP5/R4）一并评估。

### WP2 路由目录出截图身份（Backend）

改动点：

- backend/app/services/code_check_fingerprint.py:90 删 `ProjectRenderIdentity.route_catalog` 与 `build_render_context` 的 `routes` 段；`build_render_context` 的 `reads_route_context` 形参随 `routes` 段删除而失去用途，签名一并简化（`reads_route_context` 判定本身保留，仍供 `page_metadata` 使用）；`:257` 的 `build_project_render_identity` 不再解析 `build_runtime_route_config`（批量刷新少一次全项目路由解析）；`build_page_fingerprint` 与 `build_project_render_identity` 的 `runtime_routes_override` 形参删除。
- backend/app/services/code_check_service.py:282 附近保留 `candidate_runtime_routes` 供 artifact 构建使用，只断开它到身份的连线。
- backend/app/services/page_render_identity.py：保留 `routes_need_screenshot_identity` 与两个能力集合，删除 `project_route_catalog`/`RouteCatalogProjection`/`_assign_page_numbers`/`_normalize_route_node`/`_build_catalog_item`/`load_contract_fixture_cases` 等投影实现。模块 docstring 的「两侧共用 fixture 对拍」表述同步改写，仅描述闭包可读路由上下文判定的职责。
- 测试：`backend/tests/unit/test_page_render_identity.py` 保留可达性判定用例、删除投影用例；`tests/contracts/runtime-backend/route-page-number-projection.test.ts` 语义降级为 Runtime 单侧目录投影回归（改名并去掉「与 Backend 复算一致」措辞），fixture 继续约束 Runtime 自身。
- 契约测试反转：backend/tests/api/test_page_screenshot.py:1409 改为断言路由读者也**不**过期；`:1296`（自身改名）应仍过期，由 `page_metadata` 覆盖，实测确认；`:1322`、`:1248`、`:1373` 断言保持不变，但 `:1322` 用例 docstring 中「目录项变化仍会反映在目录读取页上」的说法在新语义下作废，需同步改写。
- backend/tests/integration/test_validation_screenshot_publisher.py 中依赖 `runtime_routes_override` 的两条用例随形参删除而简化，保留候选/正式身份相等的断言。
- 只读诊断脚本 `backend/app/scripts/diagnose_screenshot_freshness.py` 的归因层不再描述路由层输入。

门禁与退出条件：

- `pnpm run test:backend:unit`、`test:backend:api`、`test:backend:integration` 全绿。
- `pnpm run test:contracts`（含改名后的投影契约）全绿。
- 新增/补充断言：路由目录任意变更（其他页改名、重排 order、新增页、隐藏页）后 `screenshot_config_hash` 不变；页面自身标题变更时对读者仍变、对非读者仍不变。
- 回滚：仅影响 hash 公式，回滚代码后旧截图指针会因公式再次变化而失配，需再次重截，故要求与 WP5 同批发布。

### WP3 提示词、能力清单与开发文档（主仓）

改动点（顺序上必须晚于 WP1 合入）：

- backend/app/ai/code_standards.py 页面规范：新增「页脚页码直接渲染 `currentPage`/`totalPages`，**禁止** `currentPage > 0 ? currentPage : <常量>` 这类把序号烘进源码的兜底；未挂路由时允许 `v-if="currentPage > 0"` 隐藏页码，而不是补常量」。这是写入源码前强制读取的规范（backend/app/ai/agent_catalog.py:189），杠杆最高。
- backend/app/ai/tool_specs.py:476 `analyze_visuals` 说明补一句：截图上的页码与总页数是捕获时快照，路由增删改不触发重截，不得据截图页码反推源码有误再改写常量。同步更新 `_group` 描述与返回示例，并补工具规格防漂移测试。
- runtime/src/runtime-kit/manifest/runtime-kit.manifest.json：`useCurrentPage.v1`、`useRouteCatalog.v1`、`usePageNavigation.v1` 的 `constraints` 补取值来源与「未挂路由/隐藏路由为 0」；`return_example` 不再无条件展示 `// 3`。清单是 Agent 能力目录单一事实源。
- docs/developer/runtime/page-creation-guide.md:64 §4：写法示例保留（本来就正确），补预览与截图态语义、以及「路由变化后目录页与页码页需主动重截」。
- AGENTS.md：把「路由仅经 `page_render_identity` 的页码目录投影进入」改为「路由目录不进入截图身份；页码由 Runtime 单点解析」；删掉「页码分配规则两侧共用 `tests/fixtures/route-page-number-cases.json` 对拍」，改为「Runtime 单侧实现，fixture 只约束 Runtime」。

门禁：`pnpm run test:backend:unit`（工具规格/披露/`agent_guide` 一致性）、`pnpm run test:contracts`、`pnpm run test:repository`（文档链接与仓库边界）。

### WP4 CLI Skill（跨仓 `web-presentation-cli`）

改动点：`skills/web-presentation/references/page-generation.md:138` 保留「目录、页码和导航相关截图必须在路由挂载后执行」，补「路由改动后这些页需主动重截，平台不自动判旧」；`references/source-standards.md:68` 的 `useCurrentPage` 条目补捕获语义与禁止烘死兜底；`references/route-and-navigation.md` 同步。Skill 版本与 CLI 版本号同步点按发布流程处理。

门禁：主仓 `pnpm run test:contracts:cli-skill`；CLI 仓 `uv sync --all-packages --frozen` + `uv run pytest packages/api-client packages/cli/tests`；跨仓契约测试须取得明确主仓 commit，缺相邻主仓导致的 skip 必须报告，不得当作发布通过。

### WP5 存量收敛与发布

- 与 WP1 及第 7 节那轮改动**合并为同一次发布**：第 7 节已把 `runtime_build` 摘出截图身份，所以 WP1 的 Runtime 发布本身不改变任何截图 hash——它改变的是画面内容（页码从常量变成真实值），平台无法感知，重截前存量截图会一直「假新鲜」地显示旧值；WP2 改变 hash 公式，会让读路由的页面整批失配。分开发布只是把同一批重截拆成两次，并多出一段「截图显示错误页码却被判定最新」的窗口，因此仍要求同批。
- 上线后执行一次限定范围批量重截，使 85 页存量封面/缩略图刷新为真实页码；属写操作，需单独授权，并只用验收账号复核。
- 用只读诊断 CLI 复核：`uv run --project backend python -m app.scripts.diagnose_screenshot_freshness --format json`，确认 `同版本多 config_hash` 计数不再随时间继续增长，且路由变更后不出现新的 hash 漂移。

## 5. 门禁矩阵汇总

| 范围 | 命令 |
| :--- | :--- |
| WP1 Runtime | `pnpm run test:runtime`、`pnpm run test:runtime:gate`、`pnpm run test:render-e2e` |
| WP2 Backend 身份 | `pnpm run test:backend:unit`、`test:backend:api`、`test:backend:integration`、`pnpm run test:contracts` |
| WP3 提示词与文档 | `pnpm run test:backend:unit`、`test:contracts`、`pnpm run test:repository` |
| WP4 CLI Skill | `pnpm run test:contracts:cli-skill` + CLI 仓 pytest |
| 合入 main 前 | `pnpm run test:all`（含 E2E），再按上表补未覆盖门禁 |

## 6. 风险与未决项

- R1 `RouteInfo.component` 语义变化：已 grep 确认无读取方，但仍有测试构造体可能断言占位值，由 `test:runtime` 兜住；若发现真实依赖，改为新增 `componentPath` 字段而不动 `component`。实施时只改 `route-generator.ts:404/:425` 的 RouteInfo 侧，注意 `convertToRouteRecord`（`:144`）把 string 类型的 `config.component` 直接写入 vue-router `component` 字段，是与本计划无关的既有行为，不要触碰该链路。
- R2 隐藏页与未挂路由仍返回 0：文档必须写清楚，否则模型会另找新兜底。
- R3 假新鲜固化：若将来产品要求「页码必须对」，只能在捕获侧加校验（Runtime `render-ready` 已有 entry 身份校验先例），不得回滚 WP2。
- R4 重截窗口与批次：`6266189`（字体按实际引用过滤）与 WP2（hash 公式去掉路由段）会各自让一部分页面失配，WP1 不改变身份只改变画面。分开发布会把重截拆成多次，并延长「截图显示旧页码却被判定为最新」的窗口；要求三者同批并在同一次批量重截里收口（见 WP5）。
- R5 删除 Backend 投影后，Backend 若再需要独立页码（例如导出目录页码）必须显式重新决策，不得悄悄复刻第二套算法。
- R6 `component` 路径格式约定漂移：反查算法隐含依赖「component 值 = `@/views/<code>.<ext>`」，该格式目前由 `project_route_service.py:513` 与 `project_template_package_service.py:1286` 两个写入点维持；任一侧形态变化会让反查静默失效、页码回到 0（85 页兜底场景重演）。可在 Runtime render-ready 入口身份校验处（R3 先例）增加 component 路径形态断言，作为防漂移门禁。

## 7. 与当前未提交改动的关系

已落地待提交：`runtime_build` 出截图身份、字体按实际引用过滤（主题只取已绑定族）、检查身份与截图身份拆两套，涉及 `code_check_fingerprint.py`、`code_check_service.py`、`page_screenshot_fingerprint_service.py`、`validation_screenshot_publisher.py` 与三个测试文件，另有未跟踪的只读诊断脚本 `backend/app/scripts/diagnose_screenshot_freshness.py`。已运行：Backend 全量 unit（1067 passed）、截图/字体/主题相关 integration+api（88 passed、3 skipped）、code-check 契约与 AI 变更队列（57 passed）、身份三文件（30 passed）、只读诊断 CLI 两种格式；未运行：全量 E2E、`test:all`、跨仓契约、真实 Renderer 截图链路。

## 8. 实施记录（2026-11-04）

基线：`dev` 的 `6266189`（第 7 节那轮改动已提交）。

### 已改动的落点

- WP1：`route-generator.ts` 新增 `getPageNumberByModuleEntryPath`，`component` 改为真实组件路径（见 WP1 的实施修正）；`page-numbers.ts` 新增纯函数 `findPageNumberByModuleEntry`，路径归一复用 `runtime-preview.ts` 的 `normalizeViewModulePath`，只接受 `src/views/` 前缀入口；`useCurrentPage.v1.ts` 取 `getPageNumberByPath ?? 反查 ?? 0`，`routeInfo` 与 `title` 行为不变。
- WP2：删除 `ProjectRenderIdentity.route_catalog`、`build_render_context` 的 `routes` 段与 `reads_route_context` 形参、`build_page_fingerprint`/`build_project_render_identity` 的 `runtime_routes_override` 形参；`build_project_render_identity` 不再解析 `build_runtime_route_config`；`page_render_identity.py` 收敛为只保留 `routes_need_screenshot_identity` 与两个能力集合。`code_check_service.py` 保留 `candidate_runtime_routes` → artifact 的连线（`:297`），只断开到身份的那条。
- WP3：`code_standards.py` 页面规范两条新约束（禁止烘死兜底 + 页码是捕获时快照）；`tool_specs.py` 的 `analyze_visuals` 说明、`response_notes` 与 `image_analysis` 组描述；`runtime-kit.manifest.json` 三个页面能力的 `constraints`，`useCurrentPage.v1` 的 `return_example` 去掉无条件 `// 3`；`page-creation-guide.md` §4 与 `AGENTS.md` 多部署约束段。
- WP4：`skills/web-presentation/references/` 的 `page-generation.md`、`source-standards.md`、`route-and-navigation.md`。未改 Skill/CLI 版本号（发布时按流程同步）。
- WP2 附带核对：只读诊断脚本 `diagnose_screenshot_freshness.py` 的归因层本来就不含路由输入，无需改动。

### 已运行门禁

| 范围 | 结果 |
| :--- | :--- |
| `pnpm --filter web-runtime-vue check` + `test` | 通过（186 文件 / 1489 passed + 3 skipped，含新增 3 个测试文件）；`build` 也通过（`test:runtime:gate` 三步全绿） |
| `pnpm run test:contracts` | 通过（21 文件 / 136 用例，含改名后的 `runtime-route-page-number-projection.test.ts`） |
| `pnpm run test:backend:unit` | 通过（1065 passed，退出码 0） |
| `pnpm run test:backend:api` | 通过（359 passed） |
| `pnpm run test:backend:integration` | 通过（377 passed，9 skipped；截图/发布器两文件单跑 34 passed 无 skip） |
| `pnpm run test:repository` | 通过（9 文件 / 70 用例） |
| `pnpm run test:contracts:cli-skill` | 通过（4 passed，未 skip，相邻 CLI 仓存在） |
| CLI 仓 `uv run pytest packages/api-client/tests packages/cli/tests` | 通过（232 passed） |
| 只读诊断 `diagnose_screenshot_freshness --format summary --max-pages 12 --no-probe` | 通过：开发库 12 页中 11 页本就无截图，唯一 `hash_mismatch` 是 2026-09-28 的历史截图（`项目层` 与 stored 相同、差异在页面身份层，符合 hash 公式变更预期） |
| `test:render-e2e`（`prepare-e2e --stop-services` + `playwright --project=smoke page-screenshot.spec.ts`） | 通过（2 passed / 1.1m）：远程 Renderer PNG 链路与新增的真实页码用例。E2E 服务于本轮结束后停止，未恢复开发服务 |

新增覆盖：`page-numbers.test.ts`（反查命中、前缀形态、隐藏页、非模块入口）、`route-generator-entry.test.ts`（真实 artifact 配置下目录携带组件路径、放映 path 与 module 入口反查得到同一页码）、`useCurrentPage.v1.test.ts`（path 命中优先、反查回退、归一为 0、`routeInfo`/`title` 不变）、`test_page_screenshot.py::test_screenshot_should_stay_latest_when_route_catalog_changes`（插入/重排/隐藏/其他页改名都不判旧；自身改名对读者判旧、对非读者不判旧）、`test_visual_tool_contracts.py` 的 `analyze_visuals` 快照措辞防漂移、`tests/e2e/specs/smoke/page-screenshot.spec.ts::单页预览与截图宿主应按路由目录解析真实页码`（页脚渲染 `useCurrentPage`，同一页面在两个路由顺序下分别断言 `2 / 2` 与 `1 / 2`）。

### 未闭环项

- 真实截图链证据已闭环（2026-11-04）：`test:render-e2e` 通过，并在 `page-screenshot.spec.ts` 增补 DOM 断言——PNG 内文字不可机读，改在同一捕获宿主的 iframe 上断言页脚文本，路由换序后从 `2 / 2` 变 `1 / 2`，证明页码来自当前路由目录而非源码常量。原计划的「人工证据对」不再单独执行，需要复核像素时直接看该用例的截图附件。
- WP5 批量重截与同批发布：2026-11-04 明确决策「暂不执行，只交执行清单」，见第 9 节。`runtime_build` 已随 `6266189` 摘出截图身份，因此它和 WP1 都不再改变截图 hash；要求本轮三件同批的理由是「WP1 改变画面但身份不动 + WP2 改变公式」，分开只会把重截拆成多次并留下旧页码被判最新的窗口，不是三波全量失配。
- R6 现状：主写入方 `project_route_service.py:513` 的 `@/views/<code>.<file_type>` 已被 `backend/tests/integration/test_preview_manifest.py:507` 逐字段钉住；模板写入方 `project_template_package_service.py:1286`（固定 `.vue`）没有等价断言。Runtime 侧 `normalizeViewModulePath` 已兼容 `@/`、`/src/`、`src/`、`views/` 四种形态，并在入口不是 `src/views/` 时直接放弃反查，不会误命中。未在 render-ready 增加断言：未挂路由与格式漂移在捕获侧不可区分，加断言会把合法状态也判失败。
- 顺带发现：`projectRouteCatalog`/`buildRouteCatalogProjection`/`RouteCatalogItem` 在 WP2 之后只被契约测试消费（生产链路是 `assignPageNumbers` → `getAllRouteInfos`）。按计划保留 fixture 对 Runtime 的约束；若要按「确认无用即整链删除」处理，需要把 fixture 的期望改为页码分配结果，属另一次决策。
- `docs/developer/runtime-integration/playback-redesign/work-packages/b0-static-presentation.md:21` 仍写着「路由仍按现有可达性门控和页码目录投影纳入」，是当时的验收记录而非现行规范，未改写历史记录。

## 9. WP5 执行清单（待授权，尚未执行）

### 同批发布范围（缺一不可）

1. `6266189`：`runtime_build` 出截图身份、字体按实际引用过滤、检查身份与截图身份拆分。
2. 本轮 WP1：Runtime 捕获侧解析真实页码（需要一次 Runtime 发布，会改变 `runtime_build`）。
3. 本轮 WP2：`screenshot_config_hash` 公式去掉路由目录段。

任何一项单独上线都会额外触发一波全量失配，因此必须打进同一个平台镜像批次。CLI 仓只有 Skill 文档改动（`page-generation.md`、`source-standards.md`、`route-and-navigation.md`），未动版本号；发布时按 CLI 发布流程同步 Skill/CLI 版本与 PyPI Trusted Publisher 身份。

### 执行顺序

1. 发布前排空旧副本，Backend/Runtime/Renderer 切同版（平台内部服务不保证混版）。摘除 Renderer 前先跑 `python -m app.scripts.check_render_worker_removal`。
2. 升级后先跑只读诊断，确认桶分布：`hash_mismatch` 的预期范围是**读路由的页面**（旧公式带 `routes` 段）加上 `6266189` 字体过滤影响到的页面，不是全仓；明显超出该范围要先查原因，不要直接归因为公式变更。

   ```bash
   uv run --project backend python -m app.scripts.diagnose_screenshot_freshness --format json --max-pages 25
   ```

3. 用验收账号在**一个**项目试跑队列入口，观察 Job 终态与 PNG 后链路（封面、缩略图、列表页判旧）：

   ```bash
   POST /api/pages/batch-refresh-screenshot-jobs  {"project_id": <id>}
   ```

   `POST /api/pages/batch-refresh-screenshots` 是同步版，只适合小项目试水；两者都只处理「缺失或已过期」，按项目作用域。
4. 核对真实页码：抽查读取 `useCurrentPage` 的页（现场统计为 85 页，项目 105/126/127/128/129 各 17 页），确认第 1 页与末页页脚数字不同且与放映一致；这些页当时都写成 `currentPage > 0 ? currentPage : <常量>`，重截后应显示真实页码而不是常量。
5. 再按项目逐个批量重截，不要一次性铺满全仓；每批后用诊断脚本复核。
6. 收尾复核两条：`同版本多 config_hash` 不再随时间继续增长；改一次路由（重排或隐藏）后 `screenshot_config_hash` 保持不变。
7. 清理验收账号与工作空间、对象存储临时目录与 `.tmp` 凭证。

### 回滚与残留风险

- Runtime 侧回滚是单文件级（恢复恒 0 语义），但 `runtime_build` 与 hash 公式会再变一波，回滚同样要求三件同批。
- 假新鲜固化：重截完成前，存量截图上的页码、`总页数` 与目录文字仍是旧值；期间不得用截图 hash 断言页码正确。若产品日后要求「页码必须对」，只能在捕获侧加校验（R3），不得回滚 WP2。
- R5：Backend 若再需要独立页码（例如导出目录页码），必须显式重新决策，不得悄悄复刻第二套算法。
