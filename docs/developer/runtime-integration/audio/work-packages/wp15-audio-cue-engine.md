# WP15：Runtime `AudioCueEngine`

状态：已实现，待 WP20 真机验收。阶段：M2。主责：Runtime shell。

## 前置与输入

前置完成：[WP14](./wp14-cue-snapshot-packages.md)。

## 修改范围与交付

- 实现 shell 内部 `AudioCueEngine`，读取 artifact audio config 并通过资源映射解析 cue。
- transition 使用单通道替换策略；interaction 使用最多 4 个实例的池和同 key 80ms 节流。
- 计算 master × effects × binding gain；接入会话静音、visibility/freeze、卸载和角色变化清理。
- 缺失绑定、静态上下文、加载/解码失败、池满和静音均返回稳定 skipped/no-op，不抛到业务事件。
- 首版只使用 `HTMLAudioElement`；不引入 Web Audio、混音、ducking 或跨页 BGM。

## 完成标准

- [x] 通道替换、池复用、节流、音量和 dispose 有确定性单测。
- [x] 反复配置切换不会泄漏 Audio、监听或定时器。
- [x] capture/export/console 不创建可播放引擎。
- [x] 播放失败不阻塞导航、点击业务或页面状态机。

## 实施记录（2026-10-18）

- `core/audio/audio-config.ts` 防御性归一化 artifact 音量/gain，并提供默认静音配置；`audio-cue-engine.ts` 实现单 transition 元素、4 槽 interaction 池、80ms 节流、会话静音读取和 `suspend/resume/dispose`。
- `runtime-shell/audio/useAudioCues.ts` 只在 `allowMediaPlayback && allowAutoplay` 的执行策略下创建引擎；cue 资源必须命中当前 manifest assets，缺映射不会猜测相对路径。
- 静音读取 `getRuntimeSession(...).audioMuted`，与页面媒体共用会话状态；visibilitychange、freeze、pageshow 和卸载负责暂停/释放，恢复不补播。
- 已运行：`pnpm exec vitest run src/core/audio/audio-config.test.ts src/core/audio/audio-cue-engine.test.ts src/runtime-shell/audio/useAudioCues.test.ts`（25 passed，含 1000 次切页 + 1000 次交互实例数恒定与卸载监听清理）；`pnpm exec vue-tsc -b` 通过。
- 未运行：真实浏览器自动播放策略、跨窗口交接和长时间池复用留待 WP20。

建议提交标题：`WP15：实现 Runtime AudioCueEngine`。
