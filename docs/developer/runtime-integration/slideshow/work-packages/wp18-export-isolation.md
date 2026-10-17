# WP18：PDF、PPTX 与打印的放映隔离

状态：完成（2026-10-17）。阶段：M1。主责：Runtime / 导出。
上层工作项：G03；详见[模块计划](../renderer.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP14](./wp14-execution-contexts.md)、[WP17](./wp17-renderer-static-media.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：OffscreenPageStage、PDF、PPTX 和打印的静态上下文、取消/finally 清理及主画布状态保护。
- 交付物：放映中可生成正确顺序和内容、且不污染主会话的实际导出文件。
- 提交边界：不将网页动画写为 PPTX 原生动画，不改无关图元和字体映射。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：离屏页面不自动开始；取消/超时清理；不覆盖用户中途停止意图；主画布页码和剩余时间保持。
- [x] 验证范围：导出服务回归、取消/失败测试及实际 PDF/PPTX/打印产物验证。
- [x] 关联验收：A16；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP18：PDF、PPTX 与打印的放映隔离`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 捕获上下文：[OffscreenPageStage](../../../../../runtime/src/core/services/export/OffscreenPageStage.ts) 同时在 iframe 的 `location.search` 与 hash 路由写入 `runtimeCapture=1`。执行策略只读取 search，缺少 search 标记时离屏页面会按 `presentation` 初始化；hash 标记继续供项目壳切换到 `RuntimeCaptureLayout` 并传递 `runtimeCaptureTicket`。
- 取消链路：`CaptureOptions` 增加 `signal`，`OffscreenPageStage.capture` 把信号与期限传入 `preparePage`；PDF 与打印在逐页捕获、保存前检查取消，取消后不下载、不写完成状态。PDF/打印任务采用 `retainLockOnCancel`，取消后保持占用到 `finally` 释放离屏舞台，避免新旧任务共用 iframe。
- 主画布隔离：[BrowserPrintService](../../../../../runtime/src/core/services/BrowserPrintService.ts) 的全部页打印改为逐页使用离屏舞台，不再 `router.push` 主画布；当前页打印在项目路由下也走离屏舞台，项目外回退当前 DOM 并将动画冻结到最终状态。PDF/PPTX 原有离屏路径补齐信号与取消检查，异常、取消和超时都在 `finally` 释放舞台、模型静态帧与 iframe。
- 静态媒体：离屏页面就绪后冻结有限动画并暂停 `video`/`audio`、移除 `autoplay`，不改变播放进度；主放映的页码、剩余时间和暂停/停止意图不受导出任务影响。
- 未改协议：`packages/render-contracts` 与 Renderer 未变；网页动画和自动翻页不会写成 PPTX 原生动画。
- 验证：`pnpm run test:runtime:gate` 通过（138 files / 1049 passed / 3 skipped，构建通过），新增/更新导出服务用例覆盖信号传递、取消清理、离屏打印与主画布不导航。真实浏览器（项目 118，`auto_start=true`、2000ms、`loop=true`）暂停后执行导出：PDF 3 页、301812 字节，3 张 3840×2160 截图按封面/中页/末页顺序嵌入，封面动画块冻结在最终绿色位置；PPTX 3 页、20187 字节，无 `<p:timing>`，16:9 画布，封面绿色块存在；打印文档 3 页顺序正确；取消导出零下载且离屏 iframe 已释放。全过程主画布保持“已暂停 / 1 / 3 / 0:02”，主路由与 hash 导航计数不变，离屏舞台执行上下文始终为 `capture` 且无控制条。证据保存在 `.tmp/wp18/`。
- 未运行项：媒体结束翻页、自动结果等待与双屏同步属于 M2（WP24–WP26）；完整 M1 能力开放由 WP21 决定。
