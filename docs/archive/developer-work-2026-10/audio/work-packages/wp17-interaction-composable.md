# WP17：`useAudioCue.v1` 与点击 cue

状态：已实现，待 WP20 真机验收。阶段：M2。主责：Runtime Kit / Runtime shell。

## 前置与输入

前置完成：[WP15](wp15-audio-cue-engine.md)。

## 修改范围与交付

- 新增版本化 `useAudioCue.v1`，通过 injection 调用 shell 服务；无 provider 时返回稳定 no-op。
- API 只接受 `interaction.*` 语义 cue key，不接受 URL、资产 ID、Audio 实例或任意音量绕过；`transition.*` 由切页通道独占。
- Runtime Kit manifest 增加参数、返回、约束和显式按钮示例。
- 页面由业务 handler 主动 `playCue('interaction.confirm')`；不注册 document 全局 click 捕获。
- 静态、预览和组件宿主根据 execution policy 提供 no-op 或显式试听能力。

## 完成标准

- [x] 已绑定、未绑定、非法 key、静音、静态上下文和引擎失败均有测试。
- [x] 嵌套点击、冒泡、拖拽和 Runtime shell 控件不会被隐式触发。
- [x] 业务动作不 await 声音完成，cue 失败不改变处理结果。
- [x] manifest 与 Backend Runtime Kit 允许清单同步。

## 实施记录（2026-10-18）

- `useAudioCue.v1` 只暴露 `playCue(key)`，同步返回 `played | skipped | unavailable`；空 key 直接 no-op，缺少 shell provider 时返回稳定 `unavailable`。
- 公开层与注入服务都只接受合法 `interaction.*` key；页面传 `transition.forward` / `transition.backward` 返回 `unavailable`，不能绕过切页单通道（2026-10-19 review 修复）。
- shell 通过 `AUDIO_CUE_SERVICE_KEY` 注入交互服务；播放资格同时受执行策略和宿主 `active` 限制，普通预览、卡片、thumbnail、capture、export 均返回 `unavailable`。
- manifest 新增 `useAudioCue.v1` 的用法、返回、示例与约束；Backend 直接消费 Runtime Kit manifest 允许清单，无第二份静态目录。
- 已运行：`pnpm exec vitest run src/runtime-shell/audio/useAudioCues.test.ts src/runtime-kit/public/composables/audio/useAudioCue.v1.test.ts src/runtime-kit/manifest/runtime-kit.manifest.test.ts`（25 passed，含无 provider、空 key、可见性恢复与监听清理）；`pnpm exec vue-tsc -b` 通过。
- 未运行：在真实页面源码中由 Agent/Backend 生成并执行点击 cue 的联调留待 WP19/WP20。

建议提交标题：`WP17：公开 useAudioCue.v1 交互音效`。
