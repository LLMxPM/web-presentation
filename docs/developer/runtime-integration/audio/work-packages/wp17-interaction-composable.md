# WP17：`useAudioCue.v1` 与点击 cue

状态：待实施。阶段：M2。主责：Runtime Kit / Runtime shell。

## 前置与输入

前置完成：[WP15](./wp15-audio-cue-engine.md)。

## 修改范围与交付

- 新增版本化 `useAudioCue.v1`，通过 injection 调用 shell 服务；无 provider 时返回稳定 no-op。
- API 只接受语义 cue key，不接受 URL、资产 ID、Audio 实例或任意音量绕过。
- Runtime Kit manifest 增加参数、返回、约束和显式按钮示例。
- 页面由业务 handler 主动 `playCue('interaction.confirm')`；不注册 document 全局 click 捕获。
- 静态、预览和组件宿主根据 execution policy 提供 no-op 或显式试听能力。

## 完成标准

- [ ] 已绑定、未绑定、非法 key、静音、静态上下文和引擎失败均有测试。
- [ ] 嵌套点击、冒泡、拖拽和 Runtime shell 控件不会被隐式触发。
- [ ] 业务动作不 await 声音完成，cue 失败不改变处理结果。
- [ ] manifest 与 Backend Runtime Kit 允许清单同步。

建议提交标题：`WP17：公开 useAudioCue.v1 交互音效`。
