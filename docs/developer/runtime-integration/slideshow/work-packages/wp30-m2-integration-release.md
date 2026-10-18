# WP30：M2 媒体、双屏与捕获回归

状态：已完成（2026-10-18）。阶段：M2。主责：跨模块验证 / Renderer / 发布。
上层工作项：G04、B06（开放）、M2 出口；详见[模块计划](../acceptance.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP21](./wp21-m1-integration-release.md)、[WP22](./wp22-media-schema-permissions.md)、[WP24](./wp24-media-end-advance.md)、[WP26](./wp26-presenter-single-owner.md)、[WP27](./wp27-editor-media-form.md)、[WP28](./wp28-cli-media-mode.md)、[WP29](./wp29-mcp-media-mode.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：A18–A24 的媒体、双屏及真实捕获；每 attempt 浏览器、取消/期限、槽位/产物清理；能力 schema 2 和支持矩阵。
- 交付物：媒体结束与演讲者自动放映的完整验收报告、生命周期证据和配套发布说明。
- 提交边界：不把桌面 Chromium 验收外推为所有浏览器或全天无人值守支持。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：只有观众窗口推进；受阻/超时可恢复；截图禁播；无进程/句柄残留；验收后才声明 media_end/presenter 能力。
- [x] 验证范围：主全量与渲染专项、真实跨域/媒体/双窗口 E2E、取消期限和生命周期检查。
- [x] 关联验收：A18–A24；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP30：M2 媒体、双屏与捕获回归`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 能力开放：`SLIDESHOW_EXECUTABLE_ADVANCE_MODES` 加入 `media_end`，`presenter_auto_play=true`，`capture_auto_play` 保持 `false`；内容助手工具说明与共享契约样例同步放开，删除 AI 工具侧的未开放模式拦截。
- 兼容：schema 2 的 `advance` 始终包含 `media_timeout_ms`（默认 300000），Runtime 产物统一输出 `mediaTimeoutMs`；旧库/旧产物读取仍按 Backend 归一化补齐。
- A18–A20（单窗口媒体）：真实预览 artifact + 4.2 秒有声非静音 WebM；媒体结束 3839ms 后翻页、无媒体回退 1590ms、播放中 `audioTracks=1` 且未静音；注入受阻显示重试/下一页/停止并恢复；失效资源真实错误、1 秒超时进入错误暂停、下一页可回放；暂停后跳页保持暂停，离开页无残留播放。
- A21–A23（双窗口）：观众窗口唯一调度，媒体结束推进到下一页且控制台跟随；控制台隐藏后观众继续；观众隐藏暂停、4.5s 内不翻页、重新可见保持暂停并需显式继续；关闭观众后控制台显示“已关闭”并暂停，重开需显式开始；重复/旧 owner/旧 revision 注入不改变路径。
- A24（Renderer 生命周期）：媒体模式下截图成功（1280×720、36740 字节，画面为暂停首帧）；任务期间槽位 `busy` 且观察到 1 个 Node + 4 个 `chrome-headless-shell` 后代进程；取消任务进入 `cancelled`，期限任务以 `RENDER_ASSET_NOT_READY` 失败；结束后槽位 `idle`、后代进程与工作区文件清零。
- CLI/MCP：能力开放后，CLI 用 `wp` 完成项目默认值与路由覆盖的 media_end 写入/回滚；MCP 用生产 binding + `AsyncApiClient` 完成 capability → 配置 → 路由树 → 回滚共 11 步，全部 200 且只读 `effective_slideshow` 未回写。
- 自动化门禁：Backend 定向 49 passed；Backend 全量 1542 passed、14 skipped（补齐预览配置断言中的 `mediaTimeoutMs` 后复跑）；Editor check + 153 files/851 passed + build；Runtime check + 142 files/1098 passed/3 skipped + build；根仓 contracts 104 passed、repository 61 passed、render-contracts 22 passed、Renderer 36 passed、python-workspace 17 passed；`test:contracts:generated` 报告 Backend 与提交契约完全一致。
- 未运行/未支持：Firefox/WebKit、移动端行内播放、真实远端无人值守与独立代理服务不在本包范围；桌面 Chromium 之外的组合不列为已支持。`test:e2e:all` 未运行，因为它会停止并重置共享开发服务；A18–A24 已由独立真实预览 artifact/Chromium 专项覆盖。MCP 仓当前契约生成物仍缺外部操作元数据与放映 Schema 的合并件，本次往返用当前主仓 Schema + MCP 基线元数据在临时目录构造快照，不替代该仓后续契约门禁。
- 产物：`.tmp/wp30/`（`evidence.redacted.json`、`browser/evidence.json`、`browser/capture-evidence.json`、`browser/capture-busy.json`、13 张截图、CLI 与 MCP 往返证据）；专属账号、工作空间、项目、页面、PAT 与预览运行态已清理，`.tmp` 中未保留密码或令牌。
- 提交：`8d379a1`。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
