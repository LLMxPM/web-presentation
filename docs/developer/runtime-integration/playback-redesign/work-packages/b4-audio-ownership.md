# B4 音频所有权统一

状态：待实施。主责：Runtime media。前置：[B2](./b2-completion-aggregation.md)。出口：GB。

音频能力（资源存储、受保护分发、cue 引擎、旁白）已实现且保留，本包只重新划分所有权，消除同一媒体被多方认领。

## 交付

- 一个 `AudioBus` 统一静音、音量、播放许可状态与通道清理；旁白与自动视频归 `PageSceneSession`，切页与交互 cue 归 Deck，普通内容音频保留用户手动控制。
- 媒体用途与是否参与完成必须显式注册，停止 DOM 扫描与时间轴适配器对同一元素的重复认领；首轮每页最多一个自动发声主媒体，其余自动视频静音。
- 原 `AssetAudio/Video.v2` 承担的用途声明（如 `purpose="narration"`）迁移到保留的公开组件版本，同步 manifest 与 Backend 导入白名单；删除两个 v2 组件。
- 处理 `play()` Promise 的成功、拒绝、缓冲、结束与错误；受阻时页面进入 `blocked`，由观众窗口本地提示并等待本窗口用户手势重试、本地恢复，同时给演讲者窗口有界受阻摘要；离页后不再重试旧页面媒体。全屏请求不保证后续媒体自动播放获准，真实许可始终以 `play()` 回执为准；演讲者窗口是 `interactive-preview` 策略，不自动播放媒体。
- 截图、缩略图、检查、PDF/PPTX 与打印的执行策略统一静音且不触发 cue。取代旧 `PageMediaSession`、motion media adapter 与独立 cue 状态；资源存储与受保护文件链路继续复用。
- 删除 `page_narration`、`audio_cues` 功能门（`backend/app/schemas/audio.py`）：删门即所有环境默认开放，开发阶段接受该结论，不等 C3 证据。

## 验收

单测覆盖必需/非必需媒体、一次受阻后本地重试、静音切换、快速翻页、内容音频独立控制、cue 不阻塞完成、静态零播放。真实 Chromium 的自动播放策略、缓冲（含受保护端点慢速传输，复验 A2/G2-11）与观众窗口独立播放证据在 C3 收口。
