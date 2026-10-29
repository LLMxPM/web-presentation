# WP12：M0 配置与动画联调门槛

状态：完成（2026-10-17）。阶段：M0。主责：跨模块验证 / 发布。
上层工作项：M0 出口、A01–A08；详见[模块计划](../acceptance.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP06](wp06-template-roundtrip.md)、[WP08](wp08-ai-config-tools.md)、[WP10](wp10-editor-route-form.md)、[WP11](wp11-runtime-transition-signals.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：冻结同版 Backend/Editor/Runtime，执行 A01–A08，复核 API、Gateway、模板与真实预览/构建证据。
- 交付物：M0 验收报告和配置/动画贯通的可发布版本组合。
- 提交边界：只关闭 M0；不得据此宣布单窗口定时、媒体或双屏自动放映完成。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：所有上游工作包完成；旧项目保留原行为；M0 能力声明不包含可用的自动放映。
- [x] 验证范围：按技能选择跨模块门禁，实际预览/构建与双库迁移；发布前执行主全量及适用专项。
- [x] 关联验收：A01–A08；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP12：M0 配置与动画联调门槛`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 版本组合：同一工作树内 Backend、Editor、Runtime、Renderer 同时运行；开发库迁移至 `20261017_0100`。环境为 Windows x64、Node 24、Python 3.13、Chromium（Playwright 1.60）。
- 联调中发现并修复三处 M0 门禁问题：Editor 手写路由类型缺少 `transition`/`advance`/`effective_slideshow`，以及 Checkbox `update:modelValue` 的 `indeterminate` 联合类型；`tests/integration/test_preview_manifest.py` 的路由期望补充默认 `meta.transition`/`meta.advance`。
- 自动化门禁：
  - Backend 全量 `pnpm run test:backend` → 1534 passed、14 skipped（首轮发现并修复 `test_preview_manifest.py` 的默认 `meta.transition`/`meta.advance` 期望后重跑全绿）；放映专项 57 passed。
  - Editor `pnpm run test:editor:gate` → vue-tsc、vitest、build 全部通过。
  - Runtime `pnpm run test:runtime:gate` → 129 files / 981 passed / 3 skipped，build 通过。
  - `pnpm run test:contracts:generated` → paths=259、schemas=351、351 types 完全一致；`pnpm run test:contracts` → 104 passed；`pnpm run test:repository` → 61 passed；`pnpm run test:contracts:gateway` → 真实 Nginx 契约通过。
  - `pnpm run test:render-contracts` → 22 passed；`pnpm run test:renderer` → 27 passed；`pnpm run test:python-workspace` → 17 passed。
  - E2E `pnpm exec playwright test --config tests/config/playwright.config.ts`（auth/smoke/visual-edit/ai/runtime-heavy）→ 18 passed，含真实 PPTX、远程 Renderer PNG、三维模型像素与项目构建。
  - PostgreSQL 专项 `test:backend:pg-claim` 在本地 Docker PostgreSQL 16.14 专属临时库执行 → 10 passed、1 skipped（版本无 `thinking_enabled`）；SQLite 与 PG 旧库升级均验证回填。
- A01：开发库旧项目（2026-05/06 创建）升级后为 `fade 400ms / manual 5000ms / 不循环 / 不自动开始`，旧路由两组覆盖保持 `null`；新项目省略 `slideshow` 使用默认值；schema 1/2 模板导入补默认值。
- A02：项目默认、两组路由原始覆盖、只读生效值与预览 artifact 的 `transitionDefaults`/`playback`/叶子 `meta.transition`/`meta.advance` 一致；构建产物内联配置与预览使用同一解析器。
- A03：13 类项目级非法写入（字符串/浮点数字、布尔替代、缺组、额外字段、`media_end`、越界、`none` 非 0ms、部分组、显式 null）与 5 类路由级非法写入全部 422，旧项目/旧树未发生部分落库。
- A04：旧客户端同路径整树保存保留匹配覆盖；旧客户端重命名按新节点继承；新版客户端重命名/移动到分组时显式携带覆盖，设置保留；同一页面重复引用的两个路由覆盖互不影响。
- A05：External 创建/PATCH/configuration/route-tree、同键同载荷幂等、同键不同载荷冲突、省略与 null 不同指纹、匿名 401、跨工作空间读写 403，均符合契约。
- A06：预览 artifact 创建后 PATCH 项目，旧 artifact 仍为原配置；构建任务创建后 PATCH 项目，产物仍为任务创建时快照（job 10 / release 10，产物 15,239,278 bytes，sha256 `3194932e…591f2`）；schema 3 导出→导入→再导出等价，schema 1/2 补默认，schema 3 缺 `slideshow` 预检失败且导入 400；模板包预览 artifact 使用包内配置。
- A07：真实 Chromium 预览中 fade 500ms 实测 533ms、push 700ms 实测 712ms、`none` 无 running 阶段；反向 push 方向 `-1`；快速连跳最大 2 层、结束后仅 1 层无离场残留；`prefers-reduced-motion: reduce` 立即稳定且无 running。
- A08：应用工作空间样式与另存为样式均不修改项目 `slideshow`；复制页面到目标项目不携带路由覆盖，目标项目保持默认值。
- M0 边界：`auto_start=true`、`advance=timer 7000ms` 的预览在真实浏览器等待 8.5s 仍停留封面，未意外启动自动放映；capabilities 仅声明 `manual`，三个 auto_play 能力均为 false。
- 未运行项：Firefox/WebKit 与 PDF 产物（M1/M2 范围）、CLI/MCP 命令（WP19/WP20）、`test:render-e2e` 专项入口未单独运行（E2E smoke 已覆盖真实 PPTX/PNG/三维截图与项目构建）。证据保存在 `.tmp/wp12/`，未提交可再生成产物。
