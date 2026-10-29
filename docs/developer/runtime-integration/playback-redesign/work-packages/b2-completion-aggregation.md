# B2 完成聚合取代统一时钟

状态：实施中（2026-10-29，第一批内部会话与假任务开发验证完成）。主责：Runtime core / shell。前置：[B1](./b1-drop-arbitrary-moment.md)。出口：GB。

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

## 开发验收

单测覆盖重复 stop、开始失败、任务超时、快速离页再进入、旧 Promise 迟到、多任务只完成一次、受托管静态模式零副作用、三种推进模式、末页/循环、过渡中退出、冻结恢复不连跳、没有完成目标时的配置错误；资源轨道覆盖 `startMs`、实际完成后的非负延时、缓冲、缺失/循环/无限前驱。一个页面的旁白与视觉不得由两个控制器重复启动。准备使用正式入口的数字滚动、打字机、SVG 描边、DOM/CSS/Canvas 粒子和两条并行序列样例，完成类型与非浏览器回归；不得把新会话逻辑塞进旧 `MotionTransport`。结束时检索旧编译器、采样与 `applyAt` 无有效调用点。

本包内部先用假任务实现生命周期、时序与完成聚合，再接入 GSAP 与宿主调用点；开发出口不以实机放映为前置。样例的实际视觉效果、有限任务完成、无限装饰不阻塞、离页清理和冻结恢复统一在 C3 验证。SVG 描边样例需检查 SVG 目标支持，不能只移除属性白名单却保留仅接受 `HTMLElement` 的校验。

## 分批实施记录

### 第一批：会话与假任务（2026-10-29）

基于 B1 `925b3d7`，在 `runtime/src/core/scene/` 实现内部 PageSceneSession、宿主 slot、任务依赖校验、有效经过时钟与释放域。开发检查为 Scene 三文件 34 项单测及 Runtime check，通过；不运行浏览器。

已冻结：

- prepare 执行 define 与受管任务准备，共享最多 25 秒期限；此时只登记和准备，run 在 start 后执行。注册封口后拒绝新增任务。整个会话最多 128 项任务。
- blocking 与 ambient 使用同一套任务词汇。blocking 必须有限；scene_end 无 blocking 在 prepare 返回 SCENE_COMPLETION_REQUIRED。纯装饰执行失败不阻塞聚合；若该失败使 blocking 后继无法开始则立即失败。准备与内部暂挂钩子异常终止会话，适配器须自行消化允许降级的资源异常。
- startMs 基于本页 start，afterTrack 基于前驱实际完成，offsetMs 只能非负且必须依附前驱；缺失、循环和无限前驱在 prepare 拒绝。同步回调返回即完成，异步任务用 Promise 表达实际完成；每项最多启动一次。
- blocking 受阻与宿主冻结合并，暂停有效经过时钟并通知已启动任务的内部 setSuspended 钩子。ambient 受阻不冻结调度。最多一小时的墙钟完成期限包含受阻/冻结，防止无限等待；聚合完成后清除该期限，ambient 留到离页释放。
- stop 先取消 signal，再逆序清理；重复 stop、清理异常和迟到登记都安全。宿主每次替换分配本地 generation，旧准备/执行结果丢弃；清理回调重入切页不能覆盖更新的会话。
- slot 在 capture/export/thumbnail 下不创建会话、不执行 define；快速切到静态态先释放已有会话。

后续批次：接入 GSAP（含 SVG/回调与多序列）和版本化公开入口、替换 Deck 与预览调用端、统一模型/媒体任务接口，再同批移除旧入口、Transport/编译器/采样及 applyAt。当前仅内部假任务可运行，公开入口和宿主仍待切换，B2 尚未完成。宿主 timer/末页/循环/过渡退出等用例随接入补齐，真实表现统一 C3。
