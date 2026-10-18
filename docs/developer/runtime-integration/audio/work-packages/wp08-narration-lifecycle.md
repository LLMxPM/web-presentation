# WP08：旁白开始与页面生命周期

状态：待验收（宿主生命周期与单测完成，真实浏览器联调并入 WP12）。阶段：M1。主责：Runtime。

## 前置与输入

前置完成：[WP07](./wp07-media-purpose-session.md)。

## 修改范围与交付

- 在 `usePlaybackHost` 中把 narration 自动启动绑定到 transition settled、render-ready、当前 generation 和 execution policy。
- manual/timer 页面也可自动播放旁白；结束本身不改变推进模式。
- 接入放映暂停/恢复、visibilitychange、freeze/restore、全屏退出和宿主卸载。
- 离页时暂停、归零并释放；返回页面从头播放，不实现跨页续播。
- 自动播放拒绝投影为现有 blocked 状态，用户手势重试只作用于当前 generation。

## 完成标准

- [x] 慢资源和长过渡下旁白不会提前开始。
- [x] 快速导航、回退、重复路径和旧 Promise resolve 不产生幽灵声音。
- [x] suspend/resume 只恢复暂停前实际播放的目标。
- [x] 普通预览、Presenter console 和静态上下文不自动播放。

建议提交标题：`WP08：接入页面旁白生命周期`。

## 实施记录

- 代码版本：本工作包所在提交。
- 已实现：每个稳定放映页都在 `probeAndReport` 完成 transition settled、视觉资源就绪与当前 generation 校验后创建媒体会话；manual/timer 只自动播放 `purpose="narration"`，content 音频保持手动；Presenter console 收紧为 thumbnail 作用域。暂停/继续、visibilitychange、freeze、pageshow 与卸载沿用原宿主链路；`dispose` 后迟到的 `play()` 结果会立即 pause，离页释放时暂停并归零。自动播放拒绝进入 blocked，错误进入统一错误态。
- 已运行：
  - `pnpm exec vitest run src/core/media/page-media-session.test.ts src/runtime-shell/playback/usePlaybackHost.test.ts src/runtime-shell/presenter/PresenterConsoleView.test.ts`：55 项通过。
  - Runtime 全量：148 个文件、1178 项通过、3 项跳过。
  - `pnpm --filter web-runtime-vue check` 与触碰文件 ESLint：通过。
- 未运行：真实浏览器自动播放策略、长过渡/慢资源时序、快速导航的实机旁白窗口，留到 WP06/WP12。
