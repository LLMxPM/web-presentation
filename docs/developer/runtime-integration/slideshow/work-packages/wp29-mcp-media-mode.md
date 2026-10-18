# WP29：MCP 媒体模式扩展

状态：已完成（2026-10-18，web-presentation-mcp `773c75a`）。阶段：M2。主责：web-presentation-mcp。
上层工作项：C04（MCP）；详见[模块计划](../clients.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP20](./wp20-mcp-timer-settings.md)、[WP22](./wp22-media-schema-permissions.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：schema 2 能力、Tool Schema/输出与异步 Client 的媒体字段，补充模型侧继承和播放受阻说明。
- 交付物：可按服务端能力保存媒体配置的 MCP 兼容版本。
- 提交边界：不新增浏览器播放遥控 Tool，也不自动替换用户指定翻页模式。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：M1 服务能力缺失明确反馈；新版 advance 不丢字段；授权和幂等行为保持。
- [x] 验证范围：MCP schema 1/2 协议、权限/幂等及真实 SDK 协议 HTTP 装配往返通过；真实 Backend 媒体写入待 WP30。
- [x] 关联验收：A17、A18、A19 的 MCP 配置侧；真实播放仍由 Runtime/WP30 验收。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP29：MCP 媒体模式扩展`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 手册：项目配置/路由写说明补充 `media_end`、`media_timeout_ms` 范围、先读 `wp_get_context` 能力、循环媒体不参与等待、受阻需观众窗口操作；路由重排必须原样保留媒体 `advance`。
- 契约：schema 2 的 media_end/时限通过请求体校验并完整透传；旧契约在发出 HTTP 前拒绝未知模式与字段；策略与幂等键/空间 Header 保持。
- 验证：使用主仓 schema 2 与 mcp 分支操作元数据的定向合并契约（75 bindings/70 routes，sha256 `5ef0dfb1…`），slideshow 契约 12 passed，全量 314 passed；5 项既有失败在基线契约同样复现，与本包无关。
- 未运行：真实 Backend 的 media_end 写入（capability 未开放，WP30 复验）；生产 OAuth/Gateway 远程链路。
- 产物：MCP 仓 `.tmp/wp29/`。
- 提交：`773c75a`（web-presentation-mcp）。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
