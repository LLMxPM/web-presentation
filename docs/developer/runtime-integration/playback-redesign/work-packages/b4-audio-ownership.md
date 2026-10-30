# B4 音频所有权统一

状态：工程完成（2026-10-30，总线、显式媒体任务、内容与 cue 接线、许可提示和默认开放开发回归通过；真实发声待 C3）。主责：Runtime media。前置：[B2](./b2-completion-aggregation.md)。出口：GB。

音频能力（资源存储、受保护分发、cue 引擎、旁白）已实现且保留，本包只重新划分所有权，消除同一媒体被多方认领。

## 交付

- 一个 `AudioBus` 统一静音、音量、播放许可状态与通道清理；旁白与自动视频归 `PageSceneSession`，切页与交互 cue 归 Deck，普通内容音频保留用户手动控制。
- 媒体用途与是否参与完成必须显式注册，停止 DOM 扫描与时间轴适配器对同一元素的重复认领；首轮每页最多一个自动发声主媒体，其余自动视频静音。
- 原 `AssetAudio/Video.v2` 承担的用途声明（如 `purpose="narration"`）迁移到保留的公开组件版本，同步 manifest 与 Backend 导入白名单；删除两个 v2 组件。
- 处理 `play()` Promise 的成功、拒绝、缓冲、结束与错误；受阻时页面进入 `blocked`，由观众窗口本地提示并等待本窗口用户手势重试、本地恢复，同时给演讲者窗口有界受阻摘要；离页后不再重试旧页面媒体。全屏请求不保证后续媒体自动播放获准，真实许可始终以 `play()` 回执为准；演讲者窗口是 `interactive-preview` 策略，不自动播放媒体。
- 截图、缩略图、检查、PDF/PPTX 与打印的执行策略统一静音且不触发 cue。取代旧 `PageMediaSession`、motion media adapter 与独立 cue 状态；资源存储与受保护文件链路继续复用。
- 删除 `page_narration`、`audio_cues` 功能门（`backend/app/schemas/audio.py`）：删门即所有环境默认开放，开发阶段接受该结论，不等 C3 证据。

## 开发验收

单测与无浏览器集成测试覆盖必需/非必需媒体、一次受阻后本地重试、静音切换、快速翻页、内容音频独立控制、cue 不阻塞完成、静态零播放。真实 Chromium 的自动播放策略、缓冲（含受保护端点慢速传输，承接 G2-11）、观众窗口独立播放、旁白与 cue 真实发声证据统一在 C3 收口；媒体替身的 `play()` 成功不代表浏览器许可或实际发声已通过。

## 分批记录

第一批基于 B3 `65c556b` 实现窗口 AudioBus、显式媒体用途登记与 createSceneMediaTask 工厂。总线持有唯一元素所有权、音量/静音、真实 play Promise 回执、本地重试和冻结资格；取消立即结束自己的等待，不等待浏览器原始 Promise。任务 prepare 不播放，run 才认领后的 play，ended 才完成；区分许可受阻、缓冲与不可恢复错误，响应组件/源替换。每个 Scene 最多一个自动发声主媒体，其余自动视频静音；普通内容不得被自动认领。基础 8 项与 Runtime check 通过，组件/cue/宿主尚未接线，B4 仍实施中。

第二批基于 `c5d8100` 接入资源组件、Deck cue、Runtime 静音与根窗口生命周期。AssetAudio.v1 的 narration、AssetVideo.v1 的 automatic 只登记用途，通过 media-ready 取得目标后显式创建任务；content 使用总线内容租约且只由用户启动。总线统一 master/分组/增益与静音，Scene 自动媒体不再被旧 DOM 协调器重复暂停或恢复。删除 AssetAudio/Video.v2 与 PageMediaSession；旧 motion media adapter 已无正式宿主消费，C2 随旧时间轴清除。

当前 Runtime frame 内的许可提示按钮接入总线重试，Editor/演讲者父窗口不能代点。waiting/stalled、真实 Promise 拒绝、结束、资源切换与冻结分别处理；自身受阻不暂停原生缓冲，窗口总线与 Scene 冻结合并后恢复不补跑。cue 独立于完成聚合，仍有切页单通道、四槽交互池和 80ms 节流；旧同步 useAudioCue.v1 删除，新版本 useAudioCue.v2 返回真实许可 Promise，不预报 played。快切复用槽位以本地请求号丢弃旧回执，避免迟到回执暂停新 cue。

Backend 删除旁白/cue 功能门、阶段开放集合、相关写入与披露分支及关闭夹具；API 布尔字段只声明默认支持，均为 true。参数、资产归属与权限校验保留，检查指纹改用 audio-bus.v1 执行身份。删除关闭状态的过期测试，保留默认开放与真实参数/权限/模板导入正反例。

开发验证：完整 Runtime 183 文件 1450 项通过、3 项既有跳过，check/build 通过；相关 Backend 109 项通过；根仓音频 fixture、清单、预览与仓库约束 76 项通过；变更 Python 的未定义/未使用导入检查通过。首次完整 Runtime 的路由测试旧 config mock 缺少新增 audioConfig，改为 partial mock 后通过；文档检查发现已删文件的三条链接，更新后通过。真实 Chromium 许可、受保护媒体慢速缓冲、当前窗口独立发声和长稳仍留 C3，不把这些替身回执记作发声通过。AI/CLI 指引由 B5 联动新入口。
