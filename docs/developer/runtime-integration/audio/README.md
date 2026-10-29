# 音频资源、旁白与 cue 接入

本页是开发者定位音频实现的入口。用户操作见[放映指南](../../../user/workflows/slideshow.md)与[资源指南](../../../user/workflows/resources.md)；字段、默认值、格式和播放语义以[音频契约](./contract.md)为准。

## 当前行为

- `audio_assets`、`page_narration` 和 `audio_cues` 默认开放。Backend 的能力声明、保存门禁和构建快照消费同一能力集合。
- 页面内容音频与旁白通过 `AssetAudio.v1` 引用工作空间资源；切页和 `interaction.*` cue 由 Runtime shell 管理。
- 自动旁白和 cue 只在实际放映中执行；静态截图、PDF/PPTX、打印和检查不自动发声。
- 已有桌面 Chromium 的真实播放、受阻重试、离页停声及 cue 长稳证据。未覆盖格式、浏览器和部分生命周期场景继续按[进行中验收清单](../../projects/audio/acceptance.md)记录；不以 30 分钟旁白循环作为开放条件。

## 修改入口

| 需求 | 代码或文档入口 |
| :--- | :--- |
| DTO、能力集合与默认值 | [`schemas/audio.py`](../../../../backend/app/schemas/audio.py)、[`core/audio_defaults.py`](../../../../backend/app/core/audio_defaults.py)、[音频契约](./contract.md) |
| 写入门禁与项目设置 | [`audio_capability_gate.py`](../../../../backend/app/services/audio_capability_gate.py)、[`project_audio_settings_service.py`](../../../../backend/app/services/project_audio_settings_service.py) |
| Editor 音量与 cue 绑定 | [`ProjectPresentationConfigDialog.vue`](../../../../editor/src/components/project/ProjectPresentationConfigDialog.vue) |
| Runtime cue 和页面能力 | [`useAudioCues.ts`](../../../../runtime/src/runtime-shell/audio/useAudioCues.ts)、[`useAudioCue.v1.ts`](../../../../runtime/src/runtime-kit/public/composables/audio/useAudioCue.v1.ts) |
| 测试选择与环境 | [`dev-start-test`](../../../../.agents/skills/dev-start-test/SKILL.md) |

原 M0–M2 实施顺序与工作包在[音频进行中工作区](../../projects/audio/README.md)保留；历史联调证据见[动画前联合验收归档](../../../archive/developer-work-2026-10/pre-motion-joint-acceptance.md)。
