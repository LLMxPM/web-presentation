# WP15：Runtime `AudioCueEngine`

状态：待实施。阶段：M2。主责：Runtime shell。

## 前置与输入

前置完成：[WP14](./wp14-cue-snapshot-packages.md)。

## 修改范围与交付

- 实现 shell 内部 `AudioCueEngine`，读取 artifact audio config 并通过资源映射解析 cue。
- transition 使用单通道替换策略；interaction 使用最多 4 个实例的池和同 key 80ms 节流。
- 计算 master × effects × binding gain；接入会话静音、visibility/freeze、卸载和角色变化清理。
- 缺失绑定、静态上下文、加载/解码失败、池满和静音均返回稳定 skipped/no-op，不抛到业务事件。
- 首版只使用 `HTMLAudioElement`；不引入 Web Audio、混音、ducking 或跨页 BGM。

## 完成标准

- [ ] 通道替换、池复用、节流、音量和 dispose 有确定性单测。
- [ ] 反复配置切换不会泄漏 Audio、监听或定时器。
- [ ] capture/export/console 不创建可播放引擎。
- [ ] 播放失败不阻塞导航、点击业务或页面状态机。

建议提交标题：`WP15：实现 Runtime AudioCueEngine`。
