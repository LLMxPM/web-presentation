# WP08：旁白开始与页面生命周期

状态：待实施。阶段：M1。主责：Runtime。

## 前置与输入

前置完成：[WP07](./wp07-media-purpose-session.md)。

## 修改范围与交付

- 在 `usePlaybackHost` 中把 narration 自动启动绑定到 transition settled、render-ready、当前 generation 和 execution policy。
- manual/timer 页面也可自动播放旁白；结束本身不改变推进模式。
- 接入放映暂停/恢复、visibilitychange、freeze/restore、全屏退出和宿主卸载。
- 离页时暂停、归零并释放；返回页面从头播放，不实现跨页续播。
- 自动播放拒绝投影为现有 blocked 状态，用户手势重试只作用于当前 generation。

## 完成标准

- [ ] 慢资源和长过渡下旁白不会提前开始。
- [ ] 快速导航、回退、重复路径和旧 Promise resolve 不产生幽灵声音。
- [ ] suspend/resume 只恢复暂停前实际播放的目标。
- [ ] 普通预览、Presenter console 和静态上下文不自动播放。

建议提交标题：`WP08：接入页面旁白生命周期`。
