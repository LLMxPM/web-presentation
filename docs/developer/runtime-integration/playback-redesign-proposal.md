# 放映动画能力收敛规划

状态：**收敛后的目标方案，尚未实施**。本文件取代 2026-10-23 的十六包重规划草案（草案未入库，本地备份在 `.tmp/playback-redesign-pre-convergence/`）。用户已确认三件事：放映是平台要突破的方向；没有历史发布数据，可直接替换；**永久放弃任意时刻状态重建**。

工作包拆分见[收敛工作包清单](./playback-redesign/work-packages/README.md)。截图收敛先由 B0 建立独立静态态，再由 B1/B2 分阶段删除取帧链；默认截图与导出在每个出口都必须可用。

## 1. 定位与收敛原则

放映优先。平台的动画能力首先服务「一次演示可靠地播完并有感染力」，其次才服务静态交付。图文卡片与报告页仍然是平台内容形态，但它们对动效的需求由静态可读态与页面自有代码满足，不要求平台为其提供动画编排。

三条收敛原则：

- **不重做内核，只做削减。** threejs、slideshow、audio、motion 四条线的完成度都不低，真正缺的是「在同一个真实放映里贯通跑完一次」。先用现有能力贯通并拿到实测缺口清单，再针对缺口删代码，不先推倒重设计。
- **永久放弃任意时刻状态重建。** 这是唯一值得删掉已完成工作的地方，理由与代价见第 4 节。
- **表达力靠目录长，不靠页面代码长。** 首轮不做动效目录；但推迟不等于放弃，启动条件写在第 4 节。

## 2. 已完成资产盘点

收敛必须建立在这张表上：不重复实现已有能力，也不把「已实现未验收」当成「已交付」。

| 线 | 已实现 | 未闭环 |
| :--- | :--- | :--- |
| threejs | model3d 资源上传、GLB 校验、受保护分发、manifest、构建与资源包；`ModelViewer.vue`（1393 行）的加载、SkeletonUtils 实例克隆、解析缓存引用计数、相机与光照、视角隔离、WebGL 生命周期与上下文丢失门禁、首帧就绪探针、静态帧采集与身份（资源版本＋视角＋尺寸）；替换即全局更新语义 | A04：Three.js r186 模块级 DFG LUT 经共享纹理 `dispose` 监听持有渲染器，100 次双 GLB 进出约 +10 MiB（G2-06）；WebGL 上下文丢失未单独演练（G2-07） |
| slideshow | M0–M3 共 33 包：手动与 timer 翻页、schema 2、`media_end`、媒体超时、演讲者自动放映、全屏即放映统一模型、演讲者/观众双窗口唯一调度、同步协议 v4、构建产物放映、wake lock、freeze/pageshow 暂停与计时迟到守卫、61 分钟长稳 | 多屏 `getScreenDetails` 授权、Firefox/WebKit、移动端未验证；G2-08 BroadcastChannel/localStorage 降级与后台节流未演练；全屏入口的无人值守时长未重新累计（旧 61 分钟是窗口化自动开始）；产品级远端无人值守依赖独立代理服务，已移出 M3 |
| audio | 音频资源存储与受保护分发、引用、快照、`AudioCueEngine`、页面旁白 `PageMediaSession`、切页与点击音效、公开 API、Editor 配置、主仓 External API；CLI 0.3.4 命令与 Skill 1.4.2 | WP06/WP12 真机验收、WP20 联调未做；能力门默认只开 `audio_assets`（`backend/app/core/config.py:104` 的 `audio_dev_capabilities_enabled` 默认 False）；G2-11 受保护媒体网络缓冲未单独复现 |
| motion | G1（A01–A16）关闭、WP01–WP12 收口：`usePageTimeline.v1` 唯一时间轴、资源轨道声明（voice/audio/video/clip ＋ startMs/afterTrack/offsetMs）、`compilePageTimeline`/`digestMotionPayload`、`deriveSampledState`/`digestMotionStateProof`、`MotionTransport`（play/pause/seek/sampleAt）、受控原生视觉与属性白名单、适配器工厂与 `MotionTargetRegistry`、`Asset*.v2` 受控组件、`model-adapter.applyAt`、capture/preview bridge、render-contracts `motion_snapshot`；2026-10-22 默认开放时间轴与 `timeline_end`；固定模板下 Luna 八任务首轮 8/8、纯静态构建 8/8 | G2-01 联合创作、G2-02 生产镜像重建、G2-04 修正版长稳、G2-05 模型创作基准、G2-09 Renderer 取消清理、G2-10 组件轨道预览；指定状态截图从未开放（`backend/app/schemas/timeline.py:12` 的 `TIMELINE_CAPTURE_SNAPSHOT_ENABLED = False`） |

四条线的未闭环项高度重叠，且重叠部分是**联合与真机**，不是能力缺失。这决定了实施顺序从 A 段开始。

## 3. 目标运行模型

```text
DeckPlaybackSession       观众窗口唯一调度；全屏入口、路由、翻页过渡、推进模式
  ├─ PageSceneSession      本页视觉、三维动作、旁白/自动视频、完成与取消
  ├─ AudioBus              统一静音/解锁/音量；页面媒体与 shell 音效分通道
  └─ StaticRenderMode      独立静态态、三维初始姿态、截图与导出；不启动 Scene
```

三层所有权与正向播放是本规划保留的核心设计：每次进页创建新 generation 的 `PageSceneSession`，退出或切页即 `stop()`；会话统一持有 GSAP context、三维动作播放器、自动媒体、回调的 `AbortSignal` 与清理函数；所有完成和错误事件携带 generation，旧会话的异步结果不得影响新页面。

**跨域耦合只剩一个：本页的 `blocking` 任务是否全部完成。** 不需要全局统一时钟，不需要时间计划编译，不需要 digest，不需要状态证明。视觉、三维片段和媒体各自正向播放，由完成聚合器汇总；媒体缓冲只延后该媒体的完成，不承诺把视觉时钟回拨或精确重同步。系统可因页面隐藏而内部暂挂，但不暴露用户暂停控制。

实现上这是**削减现有 motion 内核**而不是另建一套播放内核：`core/motion` 的任务注册、清理栈、资源读取与受控组件能力保留。先让默认截图、缩略图和导出脱离 `poster.atMs/atLabel → sampleAt`，再删对外指定状态截图；新播放会话接管后才删旧 Transport 的 seek/sampleAt、时间计划编译与采样证明。

## 4. 永久放弃 / 保留 / 推迟

### 永久放弃

任意时刻状态重建整条链，包括：

- `MotionTransport` 的 `seek`（`core/motion/transport.ts:69`）与 `sampleAt`（:75）、`compilePageTimeline` 的全局时间计划与 `digestMotionPayload`、`deriveSampledState`/`digestMotionStateProof` 状态证明、`model-adapter.ts:226` 的 `applyAt`（`MotionTrackAdapter` 方法）、`capture-bridge`。
- 指定状态截图：`backend/app/schemas/timeline.py` 的 `TIMELINE_CAPTURE_SNAPSHOT_ENABLED` 与 `services/page_screenshot_job_service.py:147` 分支、render-contracts `motion.py:16-42` 的 `motion_snapshot`（`timeline_id`/`at_ms`/`at_label`/`offset_ms`/`visual_mode`）与 `schemas/execution-request.v2.json`、Backend `models/page_screenshot_job.py:47-48` 的 `motion_snapshot_json`/`_hash`、`schemas/page.py:225`、`external_api.py:291`、Runtime `core/shared/model-static-frame-contract.ts:45` 的 `motionKey`。
- 全局统一时钟、混版与回退矩阵（G2-03）、B01–B08 模型创作量化门槛（G2-05 降级为一个真实样例）、会话级自动/手动切换与 pause/resume/restart（`auto_start`）、动画最终帧或任意时刻取帧作为静态交付来源。默认海报的旧实现也使用时间轴采样，必须先由独立静态态替换，不能把默认截图一起删掉。
- 双窗口复杂同步协议：`presenter-sync-protocol.ts`（528 行）的 7 类消息、8 种播放状态、8 种命令动作（start/pause/resume/stop/retry/next/set-auto-advance/seek）与 9 种时间轴阶段。收敛为演讲者窗口发少量用户意图、观众窗口回传原子的当前页与阶段状态；删除时间轴位置、剩余时长、逐帧阶段、ack 历史和复杂重放。

任意时刻重建的放弃理由：它服务的是静态交付一致性，在放映优先定位下是次级目标；指定时刻的外部截图入口从未正式开放（capture 常量长期为 False），但默认海报的内部采样已经参与截图与导出，因此先替换默认路径才能删除；它是全局统一时钟、属性白名单和状态证明这三个复杂度来源的共同前提，删掉它，另外两个才有资格一起简化。

双窗口同步的收敛理由不同：它没有外溢（消费者全在 `runtime-shell/presenter/` 内），但现协议携带大量播放内部细节。观众窗口持有真实媒体与 `scene_end` 完成事实，因此继续作为唯一调度者；演讲者窗口只发 `start/next/stop/hold/release` 等有限用户意图。观众窗口回传原子 `{page, phase, revision, ownerId}` 与必要的 `blocked/failed` 摘要；接收端只应用更新修订，重开时请求或读取当前状态。重复消息无害，乱序旧消息会被丢弃，不建立第二套播放时钟。

代价要写清：AI 无法再验证自己生成的动画中间态，CodeCheck 与截图诊断只能证明「编译通过＋静态首帧可读」。这个上限由推迟项 D1 的动效目录化来解，不靠恢复取帧。

### 保留

model3d 资源能力全链；`ModelViewer` 的加载、实例克隆、引用计数缓存、相机与光照、视角隔离、WebGL 生命周期与上下文丢失门禁、首帧就绪探针、静态帧采集与身份；资源轨道的声明式表达（稳定 id、startMs/afterTrack/offsetMs）作为完成任务登记的形式；受控资源读取、素材鉴权与受保护文件链路；全屏即放映入口语义、双窗口唯一调度、翻页过渡与路由；`AudioCueEngine` 与旁白的资源与播放能力（重新划分所有权，能力不删）；构建产物放映、wake lock、freeze/pageshow 与计时迟到守卫；CLI 音频/构建/截图命令与 Skill。

### 推迟

- **D1 动效目录化**：入场/强调/退场/翻页过渡作为版本化 Runtime Kit 资产，页面与组件只声明「目标元素＋效果名＋参数＋顺序或触发」；Backend 可静态校验声明与默认静态态，编辑预览仍通过真实正向播放观察效果，不恢复页面或局部效果的任意进度截图；主题可指定默认动效风格；AI 从目录选而不是写 GSAP。启动条件：A/B/C 三段完成且放映可靠后，或「AI 生成动画无法验证」被实测确认为瓶颈时（以 A1 的缺口清单为准）。
- **D2 高级 Three.js 实例扩展**：对象树、材质与骨骼脚本，需先明确实例拷贝与释放规则。
- **D3 产品级无人值守放映**：远端代理、票据续签、kiosk 入口。

不在规划范围：Three.js 对象树粒子（页面粒子用 DOM、CSS 或 Canvas 自行实现）、GSAP 插件（不支持，导入校验与 CodeCheck 拒绝插件用法）。

## 5. 各域收敛决定

**三维。** 拆分 `ModelViewer.vue` 为加载与实例、相机与交互、首帧就绪、WebGL 生命周期、静态帧采集五块，并**决定 renderer 所有权**（每实例、每页共享或池化）——该选择直接决定 A04 的保留曲线，必须在 B3 给出决策、在 C3 给出修复或接受的结论。动作播放改为每实例自己的正向播放器：从实际加载的 GLB 选择片段，`AnimationMixer.update(delta)` 随帧推进，有限片段结束发一次完成事件，无限循环只作装饰；离页停止 Mixer、RAF 并释放实例资源。多个模型实例可同时播放，不需要第二套平台 Transport。资源查询中的片段索引与签名只用于开始前失效校验，不再用于每帧状态证明。静态帧身份只由资源版本、视角和尺寸决定，动作时刻不进入身份。`AssetModel.v1` 保留静态展示与可交互职责，暴露实例句柄的版本按 `.vN` 纪律新增，`AssetModel.v2` 删除。

**音频。** 一个 `AudioBus` 统一静音、音量、播放许可状态和通道清理；页面内容音频由用户手动播放，旁白与自动视频由 `PageSceneSession` 持有，切页与交互 cue 由 Deck 播放。媒体用途与是否参与完成必须显式注册，停止 DOM 扫描和时间轴适配器对同一元素的重复认领；原 `AssetAudio/Video.v2` 承担的用途声明（如 `purpose="narration"`）迁移到保留的公开组件版本。首轮每页最多一个自动发声主媒体，其余自动视频静音。媒体 `play()` 是否成功以其 Promise 结果为准；受阻时页面进入 `blocked`，由**观众窗口本地**提示并等待本窗口用户手势重试，同时向演讲者窗口回传有界受阻摘要，本地恢复不依赖跨窗口手势。全屏请求不保证后续媒体自动播放获准，始终以 `play()` 回执和真实浏览器策略为准。[MDN 的媒体播放说明](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/play)。开发阶段直接删除 `page_narration`、`audio_cues` 功能门并接受默认开放，不等 C3 证据。

**放映推进。** 只保留 `manual / timer / scene_end`，删除 `timeline_end` 与 `media_end`——完成判定统一后两者冗余。资源轨道的 `startMs` 以本页开始为基准，`afterTrack` 以先行任务实际完成为基准；`offsetMs` 只保留非负延时。旧编译器按预估时长计算的负偏移与媒体缓冲语义不再保留，详见 B2。

| 模式 | 推进条件 |
| :--- | :--- |
| `manual` | 演讲者或页面导航命令 |
| `timer` | 页面开始后经过配置的停留时间；到点即离页并取消未完成的 `blocking` 任务，不等待 |
| `scene_end` | 本页全部 `blocking` 有限视觉、三维片段和必需自动媒体结束，可配置短暂结束停留 |

无限动画、普通内容音频和短音效不参与 `scene_end`。`blocking` 由页面在播放时动态注册，因此「本页是否存在 blocking 任务」只能在会话 prepare 阶段判定；没有 `blocking` 却配置 `scene_end` 时在该阶段报配置错误，不静默退回 `timer`。prepare 与静态态各自的执行边界由 B2 定死。系统睡眠、冻结与后台节流恢复后不得连跳多页，沿用已有计时迟到守卫。

「非全屏是预览、根元素全屏才创建放映会话」保留。取消会话级自动/手动配置切换；演讲者保留仅阻止自动翻页的 `hold/release`，不暂停 Scene 动画或媒体。`hold` 期间到期的 timer 或已完成的 `scene_end` 不翻页；`release` 后重新计算当前页结束停留，不能积累过期计时并连跳。

**演讲者提供控制界面，观众窗口唯一调度。** 演讲者发送有限用户意图；观众窗口负责页面、Scene、媒体及 `scene_end`，并回传一条原子的当前页/阶段状态与必要的受阻或失败摘要。状态携带 owner 身份和单调修订，接收方拒绝旧修订；观众窗口重开后完成一次当前状态对齐，不依赖历史命令重放。控制台预览沿用 `interactive-preview` 策略，不自动播放媒体。观众窗口的全屏点击可能满足浏览器播放许可，也可能仍需本窗口另一次用户手势；不把全屏等同于音频解锁。

**静态与导出。** B0 先建立与动画时刻无关的静态态，供默认 PNG、写入附图、缩略图和 PDF/PPTX 共用。现有时间轴页面与后续 Scene 页面显式声明可读默认态、海报态或 `unsupported`；不含受托管动画的页面继续普通静态渲染。静态模式不创建播放会话，不执行受托管 Scene 回调，不播放音视频或 cue，不推进模型 Mixer；页面自行运行的 mounted 脚本、CSS/Canvas 动画必须提供静态分支，平台不宣称能阻止任意 JavaScript 副作用。Renderer 等待字体、图片、视频 poster/首帧、模型首帧与静态态就绪后截图；Runtime 不从动画代码推导海报或最终画面，海报到放映起点的交接由页面显式设计。

静态态回执区分 `ready`、`unsupported`、`failed`，不能通过图像启发式判断是否可读。`unsupported` 对应独立截图不可重试的 `STATIC_PRESENTATION_UNAVAILABLE`，不复用任务 `skipped`（现有 `skipped` 已表示快照过期、预算不足等执行原因）；诊断附图不可用不能覆盖诊断成功。缩略图显示有原因的占位，PDF/PPTX 默认整体失败并指出页码，不静默缺页。C1 在 B 段替换完成后复验这些语义与跨产物画面一致性。

**创作入口。** 新增版本化 `usePageScene.v1`，删除 `usePageTimeline.v1`，不保留并存窗口。页面在播放时注册多条 GSAP 序列、模型实例、自动媒体和回调，有限任务标 `blocking`，循环装饰标 `ambient`。放开 `native-visual.ts:14` 的 `opacity/x/y/scale/rotation` 属性白名单——它本来就不是安全边界，安全由受保护文件链路和构建期打包保证。回调取得本次会话的 signal 与清理注册，正向播放经过触发点时执行一次，退出后不再启动新工作；掉帧与内部暂挂恢复下的至多一次语义由 B2 定义。页面自行创建的监听、计时器、RAF、Canvas 或第三方实例必须登记清理；已经发生的网络或其它外部副作用无法撤销，也不参与静态截图。

**组件。** 首轮工作空间组件不纳入 Scene：组件预览宿主页不创建播放会话，组件只提供静态渲染。旧 G2-10（组件独立轨道片段预览）作废。组件需要动效时走 D1 目录化，不走页面级自由动画。

## 6. 实施顺序

三段十一包，出口与依赖见[工作包清单](./playback-redesign/work-packages/README.md)。

1. **A 段·贯通（不改内核）**：用现有能力跑通一次真实放映，重建生产镜像，验证 Renderer 取消，定出支持矩阵。这一段就是 motion G2 关闭条件的重排，产出可交付的放映与实测缺口清单。A 段不验证指定状态截图、不做混版矩阵、不跑模型创作基准——这些已被放弃。
2. **B 段·替换与削减（不新建第二套播放内核）**：B0 先接通独立静态态，默认截图与导出不再依赖时间轴海报采样；B1 删除未开放的指定时刻截图协议；B2 在新会话接管正向播放的同一切换点删除旧编译器、Transport 与内部采样；B3–B5 收敛三维、音频、Backend 配置和 Editor、Presenter、AI、CLI 调用端。每个出口保持默认 PNG 和静态导出可用，A 段的真机结论须按受影响边界复验。
3. **C 段·收口**：复验静态捕获、不可呈现语义与跨产物一致性；旧链路清零与文档；真实浏览器、独立构建产物与长稳证据一次性收口全量门禁。

直接替换期间允许 dev 的全量门禁不绿：每包只要求本包测试与生成门禁通过并记录已知红项，但 B0/B1/B2 的默认 PNG 与静态导出不能作为已知红项留待 C3。全量主门禁与专项门禁统一在 C3 收口。若某个出口不达标，回退方式是 revert 提交，不补兼容层或运行时 fallback。

## 7. 最小验收

1. 一页同时包含多 DOM 序列、两个模型实例动作、一段旁白、一个静音视频、无限装饰和切页 cue，在 Editor 预览、Runtime 全屏放映和独立构建产物三处都能播完；只有有限 `blocking` 任务决定 `scene_end`。
2. 同一页的 Renderer PNG、写入附图、缩略图、PDF/PPTX 呈现相同的可读静态态与模型初始姿态，不发声、不触发受托管 Scene 回调、不推进 Mixer；明确声明无法静态呈现时，独立截图返回不可重试的 `STATIC_PRESENTATION_UNAVAILABLE`，缩略图有原因占位，PDF/PPTX 整体失败并指出页码，不复用任务 `skipped`。
3. 内置助手、Editor 与 CLI 在同一个受控工作空间与同一样例上完成读取能力、创建/修改、等待 mutation job、回读、取得静态截图状态，能力隐藏与失败语义一致，不跨用户、不泄露存储键或票据。
4. 真实 Chromium 覆盖自动媒体受阻与观众窗口本地重试、缓冲、失败、超时、观众窗口唯一调度而演讲者窗口不播媒体、有限用户意图与原子状态的重复/乱序/重开对齐、`hold/release`、隐藏/恢复、冻结后不连跳、WebGL 上下文丢失与恢复。
5. 快速翻页、退出和重新进入不留下 RAF、定时器、媒体、WebGL 或旧回调；模型资源替换导致片段引用失效时明确报错；多实例的相机、动作、材质与销毁互不污染。
6. 生产裁剪镜像的 preview/check/build 三角色真实启动，版本身份与 Runtime Kit 一致；至少 30 分钟受控循环按既有 soak 方法记录，并给出 A04 的修复或接受结论。
7. 全仓检索无 seek、sampleAt、`motion_snapshot`、`applyAt`、`motionKey`、`auto_start`、`media_end`、`timeline_end` 的有效引用；生成物与 JSON Schema 不残留旧协议。
