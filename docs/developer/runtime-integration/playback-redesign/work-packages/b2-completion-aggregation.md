# B2 完成聚合取代统一时钟

状态：待实施。主责：Runtime core / shell。前置：[B1](./b1-drop-arbitrary-moment.md)。出口：GB。

本包是削减的核心：在 B0 静态态和 B1 外部取帧协议已替换后，把仍驱动正向播放的「全局时间计划 ＋ transport」削成「本页任务调度与完成聚合」。**这些语义由本包定死，不留给后续包各自假设。**

## 交付

- 把时间轴削减为 `PageSceneSession`：prepare、start、单次 completed、blocked/failed、幂等 stop；每次进页分配 generation，旧 generation 事件一律丢弃；受管任务注册、`AbortSignal`、清理栈、有限任务完成聚合、有界准备与完成期限。以假任务先行验证，不接入 GSAP、Three.js 或真实媒体。
- **定死 prepare 与静态态的执行边界**：prepare 是否执行 Scene 注册函数、静态态不创建会话；`blocking` 由页面播放时动态注册，因此「本页是否存在 blocking 任务」只能在 prepare 判定，无 `blocking` 却配置 `scene_end` 时在该阶段报配置错误，不静默退回 `timer`。
- **定死标记词汇**：视觉、三维与媒体共用 `blocking`/`ambient` 一套标记，媒体的「必需/非必需」映射到该词汇，不留下「blocking 的 ambient 媒体」这类歧义。
- **定死回调与计时语义**：回调正向经过触发点执行一次、掉帧与内部暂挂恢复下的至多一次保证；`timer` 到点即离页并取消未完成 `blocking` 任务，不等待。
- **定死资源轨道时序**：保留 `startMs` 时以本页开始为基准；`afterTrack` 以该任务实际完成为基准，`offsetMs` 只允许非负延时。旧编译器依赖预估结束时间计算的负偏移、媒体缓冲时的预估起点一律删除；缺失前驱、循环依赖、无限前驱与结束期限必须在 prepare 阶段报错。内部暂挂期间的延时按会话时钟处理，不在恢复时补发多次回调。
- 新增版本化 `usePageScene.v1`，就地删除 `usePageTimeline.v1` 与其 manifest 登记，不保留并存窗口；放开 `native-visual.ts:14` 的 `opacity/x/y/scale/rotation` 属性白名单；不支持 GSAP 插件，导入校验与 CodeCheck 拒绝插件用法。
- 新会话接管真实正向播放后，同批移除旧 `compilePageTimeline`、`digestMotionPayload`、`deriveSampledState`/`digestMotionStateProof`、Transport 内部 `sampleAt/seek`、各适配器 `applyAt` 和状态证明；不能在仍有播放调用点时提前删除。B0 的静态态不依赖这些模块。
- 在观众窗口建立唯一 `DeckPlaybackSession`：点击播放进入放映、过渡结束后启动当前页、退出立即停止当前页与音频；推进只支持 `manual/timer/scene_end`，删除 `timeline_end`、`media_end`、`auto_start` 会话级切换与 Scene 的 pause/resume/restart/seek；保留演讲者仅阻止自动翻页的 `hold/release`，释放后重算当前页结束停留，不连跳。保留「非全屏是预览、根元素全屏才创建放映会话」的入口语义、翻页过渡与路由；冻结与后台节流恢复后不连跳多页。generation 只服务本窗口内的快速翻页与旧会话事件丢弃，不做跨窗口 generation 协商。

## 验收

单测覆盖重复 stop、开始失败、任务超时、快速离页再进入、旧 Promise 迟到、多任务只完成一次、受托管静态模式零副作用、三种推进模式、末页/循环、过渡中退出、冻结恢复不连跳、没有完成目标时的配置错误；资源轨道覆盖 `startMs`、实际完成后的非负延时、缓冲、缺失/循环/无限前驱。一个页面的旁白与视觉不得由两个控制器重复启动。真实样例覆盖数字滚动、打字机、SVG 描边、DOM/CSS/Canvas 粒子和两条并行序列；不得把新会话逻辑塞进旧 `MotionTransport`。结束时检索旧编译器、采样与 `applyAt` 无有效调用点。
