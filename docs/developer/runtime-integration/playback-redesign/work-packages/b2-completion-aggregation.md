# B2 完成聚合取代统一时钟

状态：实施中（2026-10-30，正式 Deck 与单页 Scene 预览已接入；插件边界和样例收口中）。主责：Runtime core / shell。前置：[B1](./b1-drop-arbitrary-moment.md)。出口：GB。

本包是削减的核心：在 B0 静态态和 B1 外部取帧协议已替换后，把仍驱动正向播放的「全局时间计划 ＋ transport」削成「本页任务调度与完成聚合」。**这些语义由本包定死，不留给后续包各自假设。**

## 交付

- 把时间轴削减为 `PageSceneSession`：prepare、start、单次 completed、blocked/failed、幂等 stop；每次进页分配 generation，旧 generation 事件一律丢弃；受管任务注册、`AbortSignal`、清理栈、有限任务完成聚合、有界准备与完成期限。以假任务先行验证，不接入 GSAP、Three.js 或真实媒体。
- **定死 prepare 与静态态的执行边界**：prepare 是否执行 Scene 注册函数、静态态不创建会话；`blocking` 由页面播放时动态注册，因此「本页是否存在 blocking 任务」只能在 prepare 判定，无 `blocking` 却配置 `scene_end` 时在该阶段报配置错误，不静默退回 `timer`。
- **定死标记词汇**：视觉、三维与媒体共用 `blocking`/`ambient` 一套标记，媒体的「必需/非必需」映射到该词汇，不留下「blocking 的 ambient 媒体」这类歧义。
- **定死回调与计时语义**：回调正向经过触发点执行一次、掉帧与内部暂挂恢复下的至多一次保证；`timer` 到点即离页并取消未完成 `blocking` 任务，不等待。
- **定死资源轨道时序**：保留 `startMs` 时以本页开始为基准；`afterTrack` 以该任务实际完成为基准，`offsetMs` 只允许非负延时。旧编译器依赖预估结束时间计算的负偏移、媒体缓冲时的预估起点一律删除；缺失前驱、循环依赖、无限前驱与结束期限必须在 prepare 阶段报错。内部暂挂期间的延时按会话时钟处理，不在恢复时补发多次回调。
- 新增版本化 `usePageScene.v1`，开发分支先公开入口、manifest 与可执行调试方式，允许旧 `usePageTimeline.v1` 暂时并存；同一页只选一种编排。删除旧入口、manifest 与完整验收属于合并 main 前的门禁，不阻止开发调试。放开 `native-visual.ts:14` 的 `opacity/x/y/scale/rotation` 属性白名单；不支持 GSAP 插件，导入校验与 CodeCheck 拒绝插件用法。
- 正式放映和单页预览接管后，移除这些宿主对旧 Transport/采样/媒体会话的调用，不补运行时 fallback。B3/B4/B5 尚需替换的模型、媒体、配置与客户端消费分别由对应包移除；`compilePageTimeline`、摘要/状态证明、Transport 内部 `sampleAt/seek`、各适配器 `applyAt` 和旧公开入口的全仓清零由 C2 在合并 main 前兜底。不能要求 B2 等后续包全部完成，造成前置互等；B0 静态态保持独立。
- 在观众窗口建立唯一 `DeckPlaybackSession`：点击播放进入放映、过渡结束后启动当前页、退出立即停止当前页与音频；推进只支持 `manual/timer/scene_end`，删除 `timeline_end`、`media_end`、`auto_start` 会话级切换与 Scene 的 pause/resume/restart/seek；保留演讲者仅阻止自动翻页的 `hold/release`，释放后重算当前页结束停留，不连跳。保留「非全屏是预览、根元素全屏才创建放映会话」的入口语义、翻页过渡与路由；冻结与后台节流恢复后不连跳多页。generation 只服务本窗口内的快速翻页与旧会话事件丢弃，不做跨窗口 generation 协商。

## 开发验收

单测覆盖重复 stop、开始失败、任务超时、快速离页再进入、旧 Promise 迟到、多任务只完成一次、受托管静态模式零副作用、三种推进模式、末页/循环、过渡中退出、冻结恢复不连跳、没有完成目标时的配置错误；资源轨道覆盖 `startMs`、实际完成后的非负延时、缓冲、缺失/循环/无限前驱。一个页面的任务不得由两个控制器重复启动。准备使用正式入口的数字滚动、打字机、SVG 描边、DOM/CSS/Canvas 粒子和两条并行序列样例，完成类型与非浏览器回归；不得把新会话逻辑塞进旧 `MotionTransport`。本包出口检索正式宿主和预览无旧 Transport/采样调用；其余有效消费者明确交接 B3/B4/B5，再由 C2 全仓清零。

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

### 第二批：GSAP 正向序列（2026-10-29）

新增内部 `createGsapSceneTask`：一条序列对应一个 Scene 任务，prepare 创建暂停实例，start 由 GSAP 自己的 ticker 正向播放，真实 onComplete 结算任务。支持多条并行序列、to/from/fromTo/set、标签/位置/错峰、DOM/SVG、额外 CSS 属性与数值对象；不生成计划摘要或取帧证明。

- 有限重复参与 blocking 完成，无限 repeat=-1 只允许 ambient；内部暂挂通知直接暂停/继续当前实例，离页恢复 GSAP 管理的初始属性。
- call 与生命周期回调每会话至多一次，onUpdate 和函数值在播放时可重复执行；prepare 不执行用户回调。异步工作使用独立 Scene 任务，GSAP 回调返回 Promise 明确失败并消费拒绝。
- 回调异常经过任务 Promise 回报，不逃出 ticker；当前 render 栈退出后恢复样式，避免 onStart 异常的剩余渲染覆盖清理。DOM/SVG 目标检查同一画布，页面自有普通对象允许作为数值目标。
- 序列填充完成后封口，不能迟到追加或在离页后创建子动画；公开填充接口不提供 seek/restart 或插件注册，已知可选插件参数在 prepare 拒绝。直接 GSAP/插件导入的生产校验门禁仍随公开入口切换补齐。

使用真实 GSAP ticker 的假时钟单测，不启动浏览器。Scene 合计 47 项通过，Runtime check 通过；完整回归结果记入开发记录。GSAP 在导入时捕获 Date.now，因此测试必须在导入前安装同一只假时钟，不能只在每例 beforeEach 替换时钟后宣称已经推进真实 ticker。

下一批接页级声明与宿主生命周期；公开入口、Deck 和旧链删除仍未完成。

### 第三批：页级声明与卸载生命周期（2026-10-29）

新增内部页级 Scene 登记和 Vue 寿命绑定。挂载只保存根节点 getter 和 define，按当前画布发现唯一声明；同页的多条序列在该声明内部登记。prepare 才提供任务与视觉创作上下文，根节点未挂载时报配置错误，不提前执行 define 或构造 GSAP。

声明卸载先从发现范围移除，再通过取消信号停止绑定会话；准备中的异步 define、播放中的任务和保存过的旧声明都不能复活。迟到登记拒绝、迟到清理立即执行。声明同时登记为受管页面，capture/export/thumbnail 必须具有独立静态声明；这些场景不创建 Scene，也不执行 define。

开发验证：Scene 与 Vue 绑定共 6 文件 60 项通过；Runtime check 通过。使用真实 Vue 挂载/卸载和 GSAP 构造监听，覆盖静态零构造、画布隔离、重复声明、根节点失效及准备/播放中卸载。本批当时未暴露公共入口；该阶段的“公开与旧入口一起替换”约束已由 2026-10-30 第六批开发入口规则替代。

### 第四批：可取消资源等待（2026-10-29）

视觉资源等待新增 AbortSignal，取消以 AbortError 结束，不伪装为图片/字体失败。轮询、图片与背景探测监听、解码/字体 Promise 观察、RAF 和未胜出的超时计时统一释放；不能取消的浏览器原始加载/解码不阻塞退出，迟到拒绝被消费。将图片任务与等待句柄拆出原大文件，保留既有资源结果和回退占位语义。

现有放映宿主在停止、换页、替换准备与卸载时发送取消。失败态手动翻页先创建的目标准备，在 Router 随后提交同一路径时继续等待，不被误取消。开发验证为资源等待、宿主和 render-ready 共 4 文件 82 项通过，Runtime check 通过；Scene 的路由/过渡/资源共享准备期限由下一批接入，公开入口和旧链尚未切换。

### 第五批：页面准备屏障（2026-10-29）

新增内部 PageSceneStage，复用同一个 Scene slot，将导航提交、目标页过渡完成、DOM 提交、视觉资源就绪和页面 define/任务准备串入一次 prepare，共用原有最多 25 秒期限。prepare 不自动 start，不包含翻页时钟；现有放映控制器尚未切换，也没有新增并行控制器。普通页无 Scene 时允许 manual/timer，scene_end 仍在 prepare 明确拒绝。

静态入口在创建前拦截，既不导航也不等待资源或执行定义；准备中停止、快速往返、迟到路由/资源结果均由 slot 取消。导航被守卫拒绝、根节点缺失/替换和资源失败返回有界原因。实际过渡开始立即清空原稳定回执，卸载只清自己的回执；过渡层重新挂载后可以重新编号，不与 Scene generation 混用。

开发验证：真实 Memory Router 与 Scene 会话、可控资源和过渡子层共 2 文件 21 项通过；Runtime check 通过。覆盖准备屏障、共享期限、过渡中退出、静态零导航、快速切页、原回执失效和过渡层重挂。完整 Runtime 回归及构建结果见开发记录；未运行实机。后续继续替换正式放映/预览调用端、公开入口与导入门禁，再删除旧时间轴编译与采样链。

### 第六批：公开开发入口（2026-10-30）

按用户要求，开发分支立即公开 `usePageScene.v1`，通过 manifest 向 Backend/Agent 披露并允许页面按公开路径导入；旧入口清零改为合并 main 前的门禁。Vue 生命周期测试移至公开入口，避免只验证私有实现。正式放映宿主仍由后续批次接管，不把开发调试记为 B2 全部完成。

Vite DEV 模式提供 `window.__RUNTIME_SCENE_DEBUG__.play(scope?)/read()/stop()`，复用现有 Scene slot、prepare 和实际完成聚合。导航、卸载、重复播放、HMR 与全屏交接停止旧任务；静态策略与嵌套静态画布零播放。同一画布不能同时启动旧时间轴和新 Scene。生产构建不安装此控制台入口。使用方式见[开发调试指南](../../../runtime/scene-development.md)，实际验证结果见开发记录。

### 第七批：正式 Deck 与宿主（2026-10-30）

原 PlaybackController 就地替换为 DeckPlaybackSession，不保留双控制器。正式 usePlaybackHost 只使用 PageSceneStage，不再发现 PageMotionHandle 或创建 PageMediaSession。根元素全屏才允许启动；配置中旧 media_end/timeline_end 明确失败，不静默转 manual。Runtime 已识别 scene_end 和 completionDelayMs，Backend DTO/Editor 配置升级仍由 B5 同批完成。

完成三种推进、结束停留、末页/循环、timer 取消未完成 blocking、保持/释放、内部冻结预算与迟到计时守卫。控制条保持/释放不暂停 Scene，退出与演讲交接立即释放当前窗口任务。声明增加跨宿主单一所有权，调试和正式播放不能重复启动同一页。Presenter 现有协议暂只投影页面状态，旧暂停/定位命令明确不可用；完整协议删减由 B5 继续。

开发验证与全量结果见开发记录；实机不在本批执行。旧时间轴/媒体会话相关宿主单测随消费者删除，替换为正式 Scene 调度和宿主接线回归。

### 第八批：正式单页预览（2026-10-30）

正式预览改为 Scene 消息协议，只允许 sync/unsync/play/stop，按事件回传 generation、phase、blocking 和有界 issue；删除旧时间轴预览桥、位置轮询与暂停/定位/重播消息。开发控制台复用同一个 PageScenePreview，不再维护另一套执行逻辑。声明挂载可发现但不自动播放，目录发现排除缩略图等静态作用域。

Editor 普通与放大预览使用共享播放/停止控件；放大前停止原画布，关闭或卸载时停止 iframe。有限完成后保留停止入口以清理 ambient，状态严格核对 source、origin、协议和字段边界。父窗口首次 sync 固定 origin，unsync 释放任务；准备中取消、HMR 和页面卸载不复活旧执行。

开发验证见开发记录；实际双窗口、发声和浏览器交互仍统一交 C3。B5 继续负责持久配置、Presenter 全协议、AI/CLI 指引和其余界面收敛。
