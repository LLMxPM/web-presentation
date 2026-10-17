# WP16：单窗口入口、控制条与可见性

状态：完成（2026-10-17）。阶段：M1。主责：Runtime / Editor。
上层工作项：E03、R03（操作区）；详见[模块计划](../editor.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP09](./wp09-editor-project-form.md)、[WP10](./wp10-editor-route-form.md)、[WP15](./wp15-router-readiness-binding.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：Editor 从首页/当前页放映入口和 artifact 重建；Runtime 开始/暂停/继续/停止、页码/剩余时间、快捷键和隐藏策略。
- 交付物：从保存后的项目可实际进入和控制单窗口定时放映的完整用户路径。
- 提交边界：跨两模块只处理同一入口链路；双屏入口扩展留给 WP26，项目字段不在此重新定义。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：旧窗口仍是旧快照；切回不补跳；模式切换清理；空格不重复触发；实际发布能力未开放时入口不误导。
- [x] 验证范围：Editor 入口与 Runtime UI 单测；真实浏览器定时、可见性和三档布局。
- [x] 关联验收：A09、A11、A12、A14、A15；见[联调与验收计划](../acceptance.md)。A09/A11/A14/A15 已补真实浏览器证据，A12 仍由 WP13/WP15 的虚拟时钟与宿主集成用例覆盖。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP16：单窗口入口、控制条与可见性`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 交付（Runtime）：[PlaybackHostBridge.vue](../../../../../runtime/src/runtime-shell/playback/PlaybackHostBridge.vue) 提供开始/暂停/继续/重试/重新开始、停止、页码、状态与剩余时间；[usePlaybackHost.ts](../../../../../runtime/src/runtime-shell/playback/usePlaybackHost.ts) 增加空格切换、可见性暂停、`refresh()`、媒体协调器接入与 `playbackConfig.supported` 判定。
- 控制条：只在存在控制器时渲染；剩余时间仅由 250ms 刷新器更新，不参与调度。空格在捕获阶段处理并 `stopImmediatePropagation`，避免布局层全屏空格翻页同时触发；输入框、组合键和长按重复不处理。
- 可见性与模式：`visibilitychange` 隐藏时暂停并保留剩余时间，恢复可见不自动继续、不补跳。卡片模式将执行上下文收紧为 `interactive-preview`，策略 watcher 暂停当前页媒体并清理控制器/计时/监听；关闭卡片后重建为 `stopped`，不再次自动开始。
- 媒体协调：暂停/停止/上下文清理时只暂停当前放映页内正在播放的原生媒体，继续时仅恢复暂停前记录的元素；不启动用户手动暂停的媒体，也不影响侧栏缩略图。
- 交付（Editor）：新增 [project-presentation.ts](../../../../../editor/src/utils/project-presentation.ts)，先同步打开窗口再创建不可变 preview artifact；失败关闭空窗口并提示允许弹窗。[PagesView.vue](../../../../../editor/src/views/PagesView.vue) 从首页放映，[PageDetailView.vue](../../../../../editor/src/views/PageDetailView.vue) 下拉提供“从首页放映/从当前页放映”，当前页入口取 [page-detail-navigation.ts](../../../../../editor/src/utils/page-detail-navigation.ts) 中排序最靠前的路由绑定。入口统一命名“放映”，文案明确每次生成新快照、旧窗口不自动更新，不承诺尚未开放的发布能力。
- 修复：真实浏览器复验发现 `PageDetailView` 的 `UiDropdownMenu` 缺少 `#trigger`，导致“放映”按钮不渲染；已修正并在页面详情单测中增加触发器存在断言。
- 验证：Editor 门禁 `pnpm run test:editor:gate` 通过（153 files / 843 passed，构建通过）；Runtime 门禁 `pnpm run test:runtime:gate` 通过（137 files / 1042 passed / 3 skipped，构建通过）。新增宿主测试覆盖支持标记、可见性暂停、空格传播阻断、旧产物隐藏入口、媒体暂停/恢复；新增控制条组件测试与 Editor 入口工具测试。
- 真实浏览器：Chromium 对项目 116 的两个不可变 artifact 执行 33 项检查全部通过：1200ms 快照自动从 `/cover`→`/middle`→`/last` 后结束；3000ms 快照验证暂停/继续剩余时间、后台隐藏不补跳、全屏空格不双触发、卡片模式清理且关闭后不自动重启、停止保留当前页；Editor 页面列表与详情入口在 1440/1180/960px 可见，“从当前页放映”从第 2 页开始并打开独立快照窗口。证据保存在 `.tmp/wp16/browser-report.json`、`.tmp/wp16/shots/` 与 `.tmp/wp16/evidence.json`。
- 未运行项：A12 的真实浏览器手动连跳仍归入 WP21 联调；Renderer 静态帧、PDF/PPTX/打印隔离由 WP17/WP18 完成；观众窗口唯一调度、媒体结束翻页和双屏入口属于 M2（WP24–WP26）；CLI/MCP 配置往返在 WP19/WP20，阶段能力开放由 WP21 决定。
