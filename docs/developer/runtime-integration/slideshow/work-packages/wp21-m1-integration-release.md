# WP21：M1 单窗口联调与能力开放

状态：完成（2026-10-17；CLI `d82bf96`、MCP `fb927f2`）。阶段：M1。主责：跨模块验证 / 发布。
上层工作项：M1 出口、能力声明；详见[模块计划](../acceptance.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP12](./wp12-m0-integration.md)、[WP16](./wp16-playback-entry-controls.md)、[WP17](./wp17-renderer-static-media.md)、[WP18](./wp18-export-isolation.md)、[WP19](./wp19-cli-timer-settings.md)、[WP20](./wp20-mcp-timer-settings.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：执行 A09–A17，收集真实计时、静态产物和跨仓证据；核对 Backend/Runtime 组合后开放 timer 和单窗口能力。
- 交付物：单窗口定时自动放映的验收报告、版本矩阵和用户文档。
- 提交边界：能力开放是验收后的代码/发布交付，不在本次文档拆包时实际启用或部署。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：上游交付闭环；暂停/续播/循环可靠；捕获和导出稳定；媒体与演讲者自动放映尚未声明支持。
- [x] 验证范围：主全量门禁及改动对应专项；真实浏览器、PNG/PDF/PPTX 与 CLI/MCP 往返。
- [x] 关联验收：A09–A17；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP21：M1 单窗口联调与能力开放`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 能力开放：`build_m0_slideshow_capabilities` 更名为 `build_slideshow_capabilities`，`advance_modes` 增加 `timer`，`single_window_auto_play` 置为 true；`presenter_auto_play` 与 `capture_auto_play` 保持 false。刷新 `editor/src/types/openapi.json`（仅能力描述变化），外部 API 用例改为 M1 断言。运行中 Backend 的 `GET /api/v1/workspaces/37/capabilities` 返回上述 M1 声明。
- 真实浏览器（Chromium build 1223 / Playwright 1.60.0，headless）：项目 120（4 页含隐藏页，fade 600ms + timer 1200ms + loop + auto_start）与项目 121（单页循环）生成不可变 artifact。21 项检查全部通过：过渡后停留计时 1806ms/1866ms；播放中手动跳页与暂停中跳页后旧计时不提前推进；暂停中连跳保持单一可见层；`history.back` 后保持暂停且不补跳；末页循环周期 1756/1831/1867ms；隐藏页不进入序列（页码 1 / 3）；单页循环完成 2 次停留时间重置；无 console/page error。证据：`.tmp/wp21/browser-report.json`、`.tmp/wp21/shots/`、`.tmp/wp21/evidence.json`。
- 既有 M1 证据复用：WP16 的 33 项真实浏览器检查覆盖 A09/A11/A14/A15；WP17 的真实 PNG；WP18 的 PDF/PPTX/打印与取消隔离 37 项；WP19 的 103 项 CLI/API Client 测试与项目 119 往返；WP20 的 8 项 MCP 契约测试与项目 119 真实 Backend 往返。
- 门禁：`uv run --project backend pytest backend/tests/api/test_external_project_slideshow.py -q` → 5 passed；`pnpm run test:contracts:generated` → Backend 与提交契约一致；`pnpm run test:contracts` → 104 passed（首次全量运行因本卡外链写错在文档链接检查失败，修正后重跑通过）；Backend 1538 passed/14 skipped；Editor 153 files/843 passed 并构建通过；Runtime 138 files/1049 passed/3 skipped 并构建通过；render-contracts 22 passed；Renderer 36 passed；python-workspace 17 passed；`pnpm run test:e2e:all` → 18 passed（3.0m，含真实构建与截图/导出链路）。`pnpm run test:contracts:gateway` → 真实 Nginx + 受控上游的 OpenAPI、主题/样式/路由操作与公开路径收口检查通过；未覆盖真实部署 Gateway 到 Backend 的鉴权转发。
- 未运行：Firefox/WebKit 行为矩阵；真实部署 Gateway→Backend 的同版升级、回滚与真实 OAuth 授权；媒体结束翻页、演讲者双窗口和无人值守长期放映按阶段边界未开放。发布配套要求已写入[发布检查清单](../../../../deployment/release-checklist.md)。

## 版本矩阵

| 组件 | 版本 / 提交 | 说明 |
| :--- | :--- | :--- |
| 主仓 Backend/Editor/Runtime/Renderer | `WP21_COMMIT` | 本卡能力开放与验收证据所在提交 |
| CLI | `d82bf96` | WP19，独立仓 |
| MCP | `fb927f2` | WP20，独立仓 |
| Node / pnpm | 22.16.0 / 10.30.3 | 本地验证环境 |
| Python / uv | 3.13.3 / 0.10.10 | 本地验证环境 |
| Playwright / Chromium | 1.60.0 / build 1223 | 真实浏览器证据 |
| 服务与数据 | PostgreSQL `192.168.31.204:55432`；Backend `127.0.0.1:8000`、Editor `:5173`、Runtime `:7373`、Renderer `:7400` | 真实 Backend/Runtime 组合 |

能力声明以运行中 Backend 的 `GET /api/v1/workspaces/37/capabilities` 为准（`.tmp/wp21/capabilities-live.json`）：`advance_modes=["manual","timer"]`、`single_window_auto_play=true`、`presenter_auto_play=false`、`capture_auto_play=false`。发布时必须与含 WP13–WP18 播放控制的 Runtime 同版配套，见[发布检查清单](../../../../deployment/release-checklist.md)。
