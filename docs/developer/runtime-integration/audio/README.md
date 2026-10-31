# 音频资源、旁白与 cue 接入

本页是开发者定位音频实现的入口。用户操作见[放映指南](../../../user/workflows/slideshow.md)与[资源指南](../../../user/workflows/resources.md)；字段、默认值、格式和播放语义以[音频契约](./contract.md)为准。

## 当前行为

- `audio_assets`、`page_narration` 和 `audio_cues` 在所有环境固定开放，能力字段只声明支持范围；原阶段功能门已删除，参数、资源归属与用户权限校验保留。
- 页面内容音频与旁白通过 `AssetAudio.v1` 引用工作空间资源；自动媒体必须由页面 Scene 用 `createSceneMediaTask.v1` 显式接管，切页和 `interaction.*` cue 由 Runtime shell 与 Deck 拥有。
- 所有发声经窗口级 `AudioBus` 判定资格与重试；同页最多一个自动发声主媒体，其余自动视频必须静音。
- 自动旁白和 cue 只在实际放映中执行；静态截图、PDF/PPTX、打印和检查不自动发声。
- 收敛前已有桌面 Chromium 的真实播放、受阻重试、离页停声及 cue 长稳证据，只代表当时的旧媒体实现。AudioBus 与显式 Scene 媒体任务的真实发声、许可恢复与受保护慢速缓冲由[收敛工作包 C3](../playback-redesign/work-packages/c3-acceptance-release.md)重新实测；未覆盖格式、浏览器和生命周期场景继续按[进行中验收清单](../../projects/audio/acceptance.md)记录，不以 30 分钟旁白循环作为开放条件。

## 修改入口

| 需求 | 代码或文档入口 |
| :--- | :--- |
| DTO、能力集合与默认值 | [`schemas/audio.py`](../../../../backend/app/schemas/audio.py)、[`core/audio_defaults.py`](../../../../backend/app/core/audio_defaults.py)、[音频契约](./contract.md) |
| 总线与项目设置 | [`AudioBus`](../../../../runtime/src/core/audio/audio-bus.ts)、[`project_audio_settings_service.py`](../../../../backend/app/services/project_audio_settings_service.py)；旁白/cue 阶段功能门已删除，参数与权限校验保留 |
| Editor 音量与 cue 绑定 | [`ProjectPresentationConfigDialog.vue`](../../../../editor/src/components/project/ProjectPresentationConfigDialog.vue) |
| Runtime cue 和页面能力 | [`useAudioCues.ts`](../../../../runtime/src/runtime-shell/audio/useAudioCues.ts)、[`useAudioCue.v2.ts`](../../../../runtime/src/runtime-kit/public/composables/audio/useAudioCue.v2.ts) |
| Scene 自动媒体任务 | [`scene-media-task.ts`](../../../../runtime/src/core/media/scene-media-task.ts)、[`scene-media-registration.ts`](../../../../runtime/src/core/media/scene-media-registration.ts)、[`createSceneMediaTask.v1.ts`](../../../../runtime/src/runtime-kit/public/composables/media/createSceneMediaTask.v1.ts) |
| 测试选择与环境 | [`dev-start-test`](../../../../.agents/skills/dev-start-test/SKILL.md) |

原 M0–M2 实施顺序与工作包在[音频进行中工作区](../../projects/audio/README.md)保留；历史联调证据见[动画前联合验收归档](../../../archive/developer-work-2026-10/pre-motion-joint-acceptance.md)。
