# 音频资源、页面旁白与交互音效总计划

状态：M0/M1 实现已推进，等待 WP06/WP12 真机验收与能力开放；M2 存储、快照、cue 引擎、切页、公开 API、Editor 配置与主仓 External API 已实现，等待 WP20 联调与 CLI/MCP 独立仓交付。计划分为 M0 音频资源基线、M1 页面旁白、M2 切页与点击音效三个里程碑，共 20 个工作包。

## 1. 结论

平台应新增一等 `audio` 资源类型，但不把所有声音都建模为页面 `<audio>`：

- 页面访谈、示例录音和页面旁白使用版本化 Runtime Kit 组件 `AssetAudio.v1`，通过资源逻辑名引用 `audio` 资源。
- 页面旁白由 `AssetAudio.v1` 的 `purpose="narration"` 声明，跟随当前页面的进入、暂停、恢复和离开生命周期。
- 切页音效与点击音效是 Runtime shell 行为，使用项目 cue 绑定和统一 `AudioCueEngine`；它们不参与页面媒体完成判定。
- 页面源码通过 `useAudioCue.v1` 播放语义 cue，例如 `interaction.confirm`，不直接持有文件 URL 或资产 ID。
- 背景音乐不是当前高优先级能力。本计划不交付跨页 BGM，也不在首版 Schema 中预留不可验证字段。

这样可以同时满足复用和生命周期边界：音频文件仍由统一资源库、artifact、构建和模板包治理；旁白属于页面内容；短音效属于 shell 交互；两者不会因为 DOM 层级或切页动画互相污染。

## 2. 产品目标

1. 工作空间可以上传、预览、替换、归档和复用音频文件。
2. 页面可以用 `AssetAudio.v1` 放置有控件的内容音频，或声明一个自动随页播放的旁白。
3. 旁白只在真实放映中自动播放，在页面稳定且视觉资源就绪后开始；离页立即停止并归零。
4. `media_end` 可以等待旁白和其它参与媒体结束，浏览器阻止自动播放时沿用现有恢复流程。
5. 项目可以配置前进/后退切页音效和语义点击音效，快速操作时不叠出不可控噪声。
6. 单窗口和演讲者模式只有一个实际播放者；截图、缩略图、PDF、PPTX、打印和静态检查不播放声音。
7. 预览、构建产物、模板包和外部 API 对音频引用完整往返，不依赖开发服务器或外部 CDN。

## 3. 非目标

- 不提供音乐库、版权采购、AI 配音生成、语音识别、波形剪辑、降噪、响度标准化或服务端转码。
- 不承诺把音频嵌入 PDF/PPTX；M0–M2 只保证静态导出不播放、不阻塞且给出明确省略语义。
- 不提供逐元素时间轴、跨页无缝 BGM、旁白字幕对齐、ducking 或多轨混音。
- 不允许页面以全局 click 捕获方式自动给所有元素加声音。
- 不让页面源码写私有文件 URL、artifact 票据或 `asset_id`。

## 4. 当前能力与缺口

| 模块 | 当前能力 | 缺口 |
| :--- | :--- | :--- |
| Backend | `WorkspaceAsset` 使用字符串类型；图片、视频、模型等已有上传、历史、引用和包治理 | `AssetType`、扩展名/MIME、DTO、引用摘要和包流程没有 `audio`；没有项目 cue 绑定 |
| Editor | 资源管理器支持视频上传与 Runtime 预览；项目已有放映设置 | 没有音频类型、试听界面、cue 设置、音量与静音说明 |
| Runtime Kit | `AssetVideo.v1`、`useAssetSrc.v1` 和 manifest 已版本化 | 没有 `AssetAudio.v1`、媒体用途标记和公开 cue API |
| Runtime shell | `PageMediaSession` 已收集当前页 `audio, video`；`media_end`、暂停恢复和自动播放受阻已落地 | 会话主要服务 `media_end`；没有旁白语义、主音量/静音、cue 引擎与切页开始事件 |
| Renderer/导出 | execution policy 已区分放映、交互预览、捕获和导出 | 没有音频的显式静态策略和导出省略报告 |
| 构建/模板 | 页面和组件中的 `Asset* name` 可被静态收集 | 项目 cue 绑定不在页面源码内，需要单独加入快照、manifest、包导入导出和引用保护 |
| CLI/MCP | 可消费 External API 的资源和项目能力 | 新 `audio` 类型与项目音频配置尚未暴露和往返 |

现有媒体基础允许增量实现，但不能直接把 `<AssetAudio autoplay>` 当作旁白方案：切页宿主会暂停离场层媒体，浏览器自动播放策略不稳定，且普通手动页面当前不一定建立主动播放会话。

## 5. 统一架构

```text
WorkspaceAsset(type=audio)
        │
        ├── 页面源码：AssetAudio.v1(name, purpose)
        │       └── PageMediaSession ── narration / media_end / pause-resume
        │
        └── 项目绑定：ProjectAudioCueBinding(cue_key, asset_id)
                └── artifact audio.cues ── AudioCueEngine
                                           ├── transition channel
                                           └── interaction pool
```

详细字段、默认值和行为只在[统一契约](./contract.md)维护；阶段、模块入口和提交顺序见[实施计划](./implementation-plan.md)；执行拆分见[工作包清单](./work-packages/README.md)；最终发布门槛见[验收计划](./acceptance.md)。

2026-10-19 CLI 开发环境实测的复核结论、跨仓修复优先级和交付边界见 [CLI 实测复核与改造计划](./cli-dev-environment-remediation-plan.md)。该记录不替代音频阶段验收。

## 6. 关键设计原则

- **资源与用途分离**：`audio` 描述文件类型，`purpose` 或 cue key 描述使用语义；不新增 `narration` 资源类型。
- **旁白页面所有**：普通页面旁白写进页面源码。同一页面被多个路由复用时首版使用同一旁白；逐路由替换留待真实需求出现后单独设计。
- **短音效 shell 所有**：切页和交互音效不进入页面媒体集合，不影响 `media_end`，失败也不阻塞导航。
- **引用使用稳定身份**：数据库 cue 绑定存 `asset_id` 并做同工作空间/FK 校验；Runtime 快照只接收逻辑资源名，不接收数据库 ID。
- **实际开始点触发**：切页音效从 `PageTransitionHost` 接受一个已开始的新 generation 后触发，不监听 Router 猜测。
- **单一播放者**：演讲者模式仅观众窗口播放；控制台只发命令和显示状态。
- **静态上下文静音**：thumbnail、capture、export、print 和 check 中自动播放与 cue API 都是 no-op。
- **先 HTMLMediaElement**：首版用预加载的 `HTMLAudioElement` 与小型池，避免 Web Audio 的跨源 fetch/decode 与票据生命周期复杂度。

## 7. 里程碑

| 里程碑 | 工作包 | 可发布能力 |
| :--- | :--- | :--- |
| M0：音频资源基线 | WP01–WP06 | 管理 `audio` 资源；页面可显式播放内容音频；预览、构建和包往返完整；尚不自动播旁白 |
| M1：页面旁白 | WP07–WP12 | `purpose="narration"` 随页播放；`media_end`、暂停恢复、双窗口、全局静音和静态隔离通过验收 |
| M2：切页与点击音效 | WP13–WP20 | 项目 cue 绑定、切页音效、`useAudioCue.v1`、Editor/External API/CLI/MCP 往返和并发治理可用 |

M0、M1、M2 必须分别通过出口包验收后才能更新产品能力说明。单个 Runtime 组件或 Schema 合入不代表对应能力已经开放。

## 8. 文档维护

- 字段与运行语义变更只修改 `contract.md`，其它文档引用该契约，不复制第二份定义。
- 实施进度、提交版本、测试命令和证据回填到对应 WP 卡片；阶段结果回填到本页状态。
- 测试命令、服务探测和 E2E 环境按 [`dev-start-test`](../../../../.agents/skills/dev-start-test/SKILL.md) 执行，本专题只维护音频场景和证据要求。
- UI 实施前读取根目录 `DESIGN.md`；External API 变化同步生成 Editor 类型，并联动 `web-presentation-cli` 与 `web-presentation-mcp`。
- 只有产品能力实际开放后才更新用户文档和顶层 `README.md`，规划阶段不提前宣称支持。
