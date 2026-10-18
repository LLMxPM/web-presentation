# WP10：静音、双窗口与静态隔离

状态：待验收（静音、双窗口作用域与静态隔离已实现，真实浏览器联调并入 WP12）。阶段：M1。主责：Runtime / Renderer / 导出。

## 前置与输入

前置完成：[WP08](./wp08-narration-lifecycle.md)、[WP09](./wp09-media-end-errors.md)。实施 UI 前读取 `DESIGN.md`。

## 修改范围与交付

- 增加 Runtime 会话级 master mute，接入控制条和 `M` 快捷键；状态不写回 Backend。
- 确保 Presenter audience 是唯一媒体 owner，console 不创建可播放 session；角色变化时旧 owner 释放。
- execution policy 对 thumbnail/capture/check/PDF/PPTX/print 显式禁播并把 preload 降为 none。
- PDF/PPTX 报告 audio omitted；静态采集不等待 ended，不因音频请求失败而失败。
- 覆盖隐藏、freeze、窗口关闭、全屏退出和异常卸载清理。

## 完成标准

- [x] 静音按钮、快捷键、暂停和播放状态不互相混淆。
- [ ] Presenter 刷新、重连和降级时任一时刻最多一个发声窗口。
- [x] Renderer/PDF/PPTX/print 无播放、无 blocked UI、无私有票据泄漏。
- [x] 控制条符合设计规范和键盘可访问性要求。

建议提交标题：`WP10：收敛旁白静音与执行上下文`。

## 实施记录

- 代码版本：本工作包所在提交。
- 已实现：`usePlaybackHost` 增加本地 master mute，控制条新增带 `aria-pressed` 的静音按钮和文档级 `M` 快捷键；快捷键跳过输入目标、系统组合键和重复按键。静音只覆盖元素 muted，解除时恢复页面自身声明，新加入媒体继承当前会话静音。Presenter console 根作用域从 `interactive-preview` 收紧为 `thumbnail`，当前页/下一页预览和观众窗口不再形成第二个发声者。静态 audio 继续由 execution policy 强制 `preload=none`、禁播；WP05 的 PPTX omitted、打印隐藏和执行上下文测试保持通过。
- 已运行：
  - `pnpm exec vitest run src/runtime-shell/playback/PlaybackHostBridge.test.ts src/runtime-shell/presenter/PresenterConsoleView.test.ts src/runtime-shell/playback/usePlaybackHost.test.ts src/core/media/page-media-session.test.ts`：61 项通过。
  - Runtime 全量：148 个文件、1178 项通过、3 项跳过。
  - `pnpm --filter web-runtime-vue check` 与触碰文件 ESLint：通过。
- 未运行：Presenter 刷新/重连/降级、真实多显示器与全屏退出时“最多一个发声窗口”的实机验证，留到 WP12；该完成标准保持未勾选。
