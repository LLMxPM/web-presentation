# WP10：静音、双窗口与静态隔离

状态：待实施。阶段：M1。主责：Runtime / Renderer / 导出。

## 前置与输入

前置完成：[WP08](./wp08-narration-lifecycle.md)、[WP09](./wp09-media-end-errors.md)。实施 UI 前读取 `DESIGN.md`。

## 修改范围与交付

- 增加 Runtime 会话级 master mute，接入控制条和 `M` 快捷键；状态不写回 Backend。
- 确保 Presenter audience 是唯一媒体 owner，console 不创建可播放 session；角色变化时旧 owner 释放。
- execution policy 对 thumbnail/capture/check/PDF/PPTX/print 显式禁播并把 preload 降为 none。
- PDF/PPTX 报告 audio omitted；静态采集不等待 ended，不因音频请求失败而失败。
- 覆盖隐藏、freeze、窗口关闭、全屏退出和异常卸载清理。

## 完成标准

- [ ] 静音按钮、快捷键、暂停和播放状态不互相混淆。
- [ ] Presenter 刷新、重连和降级时任一时刻最多一个发声窗口。
- [ ] Renderer/PDF/PPTX/print 无播放、无 blocked UI、无私有票据泄漏。
- [ ] 控制条符合设计规范和键盘可访问性要求。

建议提交标题：`WP10：收敛旁白静音与执行上下文`。
