# WP15：Router、页面就绪与调度桥接

状态：完成（2026-10-17）。阶段：M1。主责：Runtime。
上层工作项：R02（宿主接入）、G01（稳定页）；详见[模块计划](../runtime.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP05](./wp05-artifact-build-config.md)、[WP11](./wp11-runtime-transition-signals.md)、[WP13](./wp13-playback-state-machine.md)、[WP14](./wp14-execution-contexts.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：Router 会话绑定、现有叶子目录、页面 DOM/必要资源就绪、过渡信号及错误恢复；一次性 auto_start 接入。
- 交付物：真实页面就绪并结束过渡后才开始停留计时的运行链路。
- 提交边界：不复制第二套目录或直接绕过 navigateRuntimePage；不实现媒体结束和观众窗口调度。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：加载不吃停留时间；手动跳页、浏览器导航和卸载作废旧任务；资源失败暂停且可见。
- [x] 验证范围：组合式/宿主 integration，延迟加载、旧事件、路由失败与捕获禁推进测试。
- [x] 关联验收：A09、A10、A12、A13、A16；见[联调与验收计划](../acceptance.md)。真实浏览器证据在 WP21。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP15：Router、页面就绪与调度桥接`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 交付：[usePlaybackHost.ts](../../../../../runtime/src/runtime-shell/playback/usePlaybackHost.ts) 与 [PlaybackHostBridge.vue](../../../../../runtime/src/runtime-shell/playback/PlaybackHostBridge.vue)，在普通放映布局中接入调度；观众窗口本包不挂载调度桥，演讲模式保持手动。
- 目录：复用 `getRouteInfosSortedByPageNumber()` 与现有 `navigateRuntimePage`，`RouteInfo` 新增叶子页生效 `advance`；隐藏页和分组不进入序列。`playbackConfig` 暴露项目 `autoStart`/`loop`。
- 就绪时序：路由路径变化先 `notifyPageChange`；等待 `RuntimePageStage` 的 `settled`（路径匹配、新事件）后，定位 `.runtime-page-print-source`，再用限定根节点的视觉资源探针（图片/背景/图表/字体，15s 上限、不等待整页动画）确认就绪，最后上报 `reportReady`。
- generation：每次尝试记录控制器 path/generation；旧页 settled、旧探测结果、卸载后的 Promise 都不会上报。资源失败、节点缺失、路由错误进入 `error` 并在宿主显示可见告警，不创建推进计时。
- 自动开始：在 `onMounted` 占用 `RuntimeSession.autoStartAttempted`，每个 Router 会话只尝试一次；仅当执行策略允许自动推进且 `auto_start=true` 时启动。卡片/缩略图/捕获上下文不创建控制器或计时句柄。
- 验证：新增 9 个宿主集成测试（自动开始一次、延迟就绪、旧 settled、资源失败、节点缺失、导航错误、重新挂载、捕获禁推进、目录构建）；专项 48 passed；Runtime 完整门禁 136 files / 1036 passed / 3 skipped，构建通过。证据保存在 `.tmp/wp15/`。
- 未运行项：可见性暂停与控制条（WP16）、Renderer/导出（WP17/WP18）、真实浏览器 A09/A10/A12/A13（WP21）、观众窗口唯一调度与媒体（M2）。
