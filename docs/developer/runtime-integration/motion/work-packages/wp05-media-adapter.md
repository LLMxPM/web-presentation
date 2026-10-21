# WP05 音视频同步适配器

状态：待验收（代码与单测完成，真实媒体/HTTP Range 未执行）。主责：Runtime media。前置：[WP03](./wp03-transport-targets.md)。

## 输入与落点

复用媒体守卫、AudioViewer/VideoViewer 和 PageMediaSession。新适配器接入独占目标注册表，不建立第二套会话来同时控制同一元素。

## 交付

- 实现文件音视频的 metadata/解码准备、裁切、有限重复、rate、主媒体进度映射和结束交接。
- 保留 narration 能力开关、单旁白与有声目标数量限制、项目音量、静音和用户手势要求；普通内容音频保持手动。
- required 媒体缓冲暂停同步集合，optional 媒体按明确策略冻结/跳过；恢复不覆盖用户暂停意图。
- 实时进度以真实媒体为准，按后续验证确定的阈值校正漂移，不在 RAF 中逐帧写 currentTime；G0 未冻结性能预算。
- seek 等待相应 revision 的 seeked 和视频目标帧确认，支持经过验证的帧回执回退；超时、取消、快速换源与旧回执均有界。
- 静态 sample 只解码与定位，不播放声音；同步目标原生控件的进度操作统一进入 transport。

## 验证与通过条件

真实浏览器覆盖 A06–A10：有声 autoplay 拒绝、手势恢复、慢资源、重复 waiting、离页、裁切边界与主媒体正常/异常结束。HTTP 使用受保护素材真实 HEAD/Range，不能只用 data URL 或同源短文件替代全部场景。

记录漂移、seek 延迟和缓冲恢复数据，在验收计划中明确后续阈值与环境；暂停过的独立媒体不能因时间轴 resume 被启动。

## 不包含

跨页 BGM、音量 ducking、多轨混音、直播、外部 iframe、自动字幕时间生成和 sample 期间试听。

## 实施记录

- 代码版本与测试媒体身份：`runtime/src/core/motion/media-adapter.ts`；按 `data-runtime-asset-name` 定位 AssetAudio/AssetVideo，显式 selector 优先。
- 实际命令、结果、时序和声音/静音证据：`pnpm --filter web-runtime-vue exec vitest run src/core/motion`，WP05 6 项通过；覆盖裁切/重复/速率映射、资源定位与 PageMediaSession 独占过滤。
- 未覆盖项：真实浏览器 autoplay 拒绝、缓冲恢复、seeked/rVFC 帧确认、HTTP HEAD/Range 与漂移数据尚未采集；当前 drift 阈值 120ms 仅作为实现常量，待 WP12 实测调整。
