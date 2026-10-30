# Motion 收敛开发记录

本记录承接[工作包清单](./work-packages/README.md)。实机、生产镜像、独立产物和长稳证据由 C3 统一取得，工程完成不代表实机通过。

现行开发入口规则于 2026-10-30 按用户要求调整：功能分支先公开入口、manifest 与可执行调试方式，允许新旧入口暂时并存；旧链清零和完整验收在合并 main 前收口。下文早期记录中的“暂不公开以避免并存”仅保留为历史，不再约束后续开发。

## A1 现状核对（2026-10-29）

核对基线：`630d429`，工作区干净；未启动服务、未重置数据库。

| 范围 | 已核对的源码与事实 | 承接 |
| :--- | :--- | :--- |
| 公开编排 | [usePageTimeline.v1](../../../../runtime/src/runtime-kit/public/composables/motion/usePageTimeline.v1.ts) 挂载时执行 define、编译和构造 transport，静态准备调用 posterTimeMs 的 sampleAt | B0 隔离静态执行，B2 替换播放入口 |
| 静态就绪 | [render-ready](../../../../runtime/src/core/utils/render-ready.ts) 调用 [motion readiness](../../../../runtime/src/core/motion/readiness.ts)，静态态依赖时间轴编译和准备 | B0 独立静态登记与回执 |
| 执行策略 | [execution-policy](../../../../runtime/src/core/execution/execution-policy.ts) 区分 capture/export/thumbnail；[execution-scope](../../../../runtime/src/core/execution/execution-scope.ts) 只允许嵌套收紧 | B0 复用，B5 删除死标志 |
| 导出 | [OffscreenPageStage](../../../../runtime/src/core/services/export/OffscreenPageStage.ts) 固定捕获 iframe，先 finish 原生动画再应用时间轴 snapshot | B0 默认静态态，B1 删除指定时刻入口 |
| 资源等待 | [visual-assets](../../../../runtime/src/core/utils/visual-assets.ts) 等待有限动画结束，同时已有字体、图片与媒体首帧等待 | B0 静态模式跳过动画等待，保留资源等待 |
| 缩略图 | [ViewPreview](../../../../runtime/src/runtime-shell/preview/ViewPreview.vue) 提供 thumbnail 策略；[PreviewThumbnail](../../../../runtime/src/runtime-shell/layouts/PreviewThumbnail.vue) 承载小画布 | B0 静态准备与原因占位 |
| Renderer | [render_ready](../../../../renderer/wp_renderer/engine/render_ready.py) 收内容错误；[executor](../../../../renderer/wp_renderer/engine/executor.py) 诊断前判就绪；[joint_capture](../../../../renderer/wp_renderer/engine/joint_capture.py) 隔离附图失败 | B0 分离不可呈现与诊断失败，B1 删 motion_snapshot |
| 远程契约 | [screenshot](../../../../packages/render-contracts/src/render_contracts/screenshot.py) 只有 available/failed/skipped；[errors](../../../../packages/render-contracts/src/render_contracts/errors.py) 单源映射错误语义 | B0 增加 unavailable 与稳定原因码，同步 JSON Schema |
| 写入附图 | [validation_screenshot_publisher](../../../../backend/app/services/validation_screenshot_publisher.py) 已有候选身份与发布围栏，缺失图片目前变为 pending/skipped | B0 新增不可呈现，保留诊断成功与围栏 |
| 正向播放 | [usePlaybackHost](../../../../runtime/src/runtime-shell/playback/usePlaybackHost.ts) 同时发现时间轴和页面媒体，旧完成与 Presenter 协议仍存在 | B2/B4/B5 唯一所有者，B0 不拆旧播放 |
| 三维 | 模型静态帧身份仍有 motionKey；资源、实例克隆、共享缓存与首帧能力保留 | B1 清动作身份，B3 决定 renderer 所有权，C3 测 A04 |
| AI/客户端 | animation_authoring_standard/tool_specs、Editor 生成 DTO、CLI 指引仍面向旧时间轴 | B0 补静态声明，B5 切 Scene；CLI 在独立仓维护 |

风险归属：静态声明缺失、超时及各产物不一致由 B0/C1 处理；重复媒体 owner 由 B4 处理；Presenter 由 B5 处理；A04 与 WebGL 恢复由 B3 实现、C3 实测。Renderer 取消、受保护媒体缓冲、播放许可、生产裁剪依赖和联合创作统一留给 C3。历史 G1/G2 只作风险输入，未复现的边界保持待验证。

## A2 契约与验收设计（2026-10-29）

| 契约 | 冻结责任 | 消费者及开发检查 |
| :--- | :--- | :--- |
| 独立静态呈现 | B0：useStaticPresentation.v1；default/poster/unsupported 声明；ready/unsupported/failed 回执 | render-ready、ViewPreview、离屏导出、Renderer；作用域、超时、零时间轴构造 |
| 不可呈现 | B0：STATIC_PRESENTATION_UNAVAILABLE 不可重试；截图 unavailable，诊断独立保留 | RenderContracts、Renderer、publisher、Editor DTO；JSON Schema 对拍 |
| Scene | B2：生命周期、generation、blocking/ambient、回调清理、实际完成依赖与非负延时 | shell、模型、媒体、预览；假任务、迟到回执、一次完成与静态零副作用 |
| 模型 | B3：独立 Mixer、实例句柄、共享资源释放与 renderer 所有权 | Scene、静态帧；实例隔离、替换失效 |
| 音频 | B4：AudioBus、用途、单一发声主媒体与本地重试 | Scene、Deck、Presenter；媒体状态、取消、静态零播放 |
| 配置与同步 | B5：manual/timer/scene_end、最小意图、owner/revision 原子状态 | Backend、Editor、CLI、独立构建；生成契约、重复乱序与版本失败语义 |

共同样例：一个小项目中，同一页覆盖多 DOM 序列、数字滚动、打字机、SVG 描边、页面粒子、两个模型动作、旁白、静音视频和无限装饰；相邻页验证导航、结束停留和切页 cue。每页显式声明静态态与 blocking 完成条件。负例覆盖缺失静态声明、unsupported、资源失败、无限前驱、旧片段签名与非法推进模式。B2/B5 准备源码，C3 经 Editor/内置助手/CLI 实际创作。

| C3 组 | 证据与预期 | 失败责任 |
| :--- | :--- | :--- |
| 创作链 | 同工作空间样例读取能力、修改、等待任务、回读、PNG/附图、权限与隐藏能力 | B0/B5 |
| 静态 | PNG、附图、缩略图、PDF/PPTX 内容一致且零播放；不可呈现与资源失败独立 | B0/C1 |
| 播放与多窗口 | 有限完成、ambient 不阻塞、唯一观众 owner、乱序/重开/降级、hold/release | B2/B5 |
| 媒体 | 本地手势恢复、受保护慢传输、旁白/cue 实际发声 | B4 |
| 三维 | 首帧、双实例、片段失效、WebGL 恢复与 A04 曲线 | B3 |
| Renderer | 取消后 attempt、进程/僵尸、临时文件、idle 槽位与迟到产物 | C1 |
| 产物 | 最终镜像三角色和身份、独立 ZIP 全屏/双窗口/媒体/静态导出 | B2–B5/C2 |
| 长稳 | 最终候选至少 30 分钟，堆、RAF/计时器、dropped-frame、媒体/WebGL | 对应责任包 |

支持矩阵初始状态：桌面 Chromium、单窗口/同浏览器双窗口、Runtime 全屏和独立构建为目标支持，全部待 C3；多屏授权、Firefox/WebKit、移动端与操作系统真实睡眠未验证，不作支持承诺。

开发入口复用 Runtime execution/render-ready/OffscreenPageStage/motion/manifest 单测，Renderer readiness/joint_capture/static_media 单测，RenderContracts DTO/JSON Schema 对拍，Backend publisher/code_check/指纹/队列测试，以及 Editor 类型、单测与生成门禁。旧浏览器夹具由 C2 适配、C3 正式运行，A 段不补跑旧链路。

## B0 独立静态呈现（2026-10-29）

实现基于 `2587f06`；源码与本记录同批提交。新增版本化 `useStaticPresentation.v1`、同根声明要求、静态准备期限与取消、逐画布就绪聚合。capture/export/thumbnail 不执行时间轴 define、编译或采样；页面自有 CSS/Canvas 与 mounted 副作用使用显式静态分支。

默认 PNG、同 attempt 附图、缩略图与离屏导出共用独立静态态。移除导出动画 finish 与等待终点，Renderer 不再借 Playwright 快进；有路由的当前页导出统一走离屏舞台。导航撤销旧回执、忽略迟到准备，批量 PDF 任一页失败即整体失败；PPTX/打印静态准备错误携带页码。旧显式选择器暂留至 B1，旧交互预览与放映内部采样暂留至 B2/B5。

冻结静态回执 `ready/unsupported/failed`；不可呈现使用不可重试的 `STATIC_PRESENTATION_UNAVAILABLE`。Renderer 附图与写入结果增加 `unavailable`，保留已完成布局，不伪装为 pending/skipped。捕获策略升级 `page-static-capture.v2`，共享常量驱动缓存身份、调度与 Worker 能力；发布权限、候选版本及默认指针围栏保留。

开发验证：`pnpm run test:runtime` 169 文件、1373 项通过、3 项既有跳过；首轮旧 S0 取消测试仍走真实舞台而超时，调整为受控静态准备后完整重跑通过，保留转换/打包期间取消和零下载断言。`test:renderer` 55 项、`test:render-contracts` 35 项、Backend DTO/清单/附图发布 24 项、`test:repository` 8 文件 63 项通过；Runtime check/build、Editor check、Editor API 生成与 `test:contracts:generated` 通过。Renderer 测试替身延后到槽位释放后再撤销，修复单测误入真实执行器的竞态。

未运行：真实浏览器/Renderer PNG、缩略图像素、实际 PDF/PPTX/打印产物、媒体禁播、生产镜像、独立构建产物、多窗口、WebGL 与长稳；全部移交 C3。本批未启动应用服务、未重置开发数据。

## B1 删除指定时刻截图协议（2026-10-29）

实现基于 B0 `4d05161`；源码与本记录同批提交。删除 Runtime 捕获桥、静态帧 motionKey、截图请求/响应选择器、Backend 任务持久化字段、Renderer 消费和控制契约采样回执。内部及 External API 明确返回 422；控制协议 v1/v2 与 Python DTO 对旧字段（含 null）均拒绝，operation_options 同样封口。能力自省删除 capture_snapshot，Editor OpenAPI/API 类型与 External API 文档同步。CLI/MCP 后续接入不得再读取这三个旧字段；MCP 不纳入本轮交付，CLI Scene 指引由 B5 维护。

迁移 `20261029_0100` 在临时 SQLite 库从上一版本真实升级：JSON null 与 SQL NULL 默认任务不取消，旧活跃选择器任务取消，已完成任务和 PNG 引用保留；去重恢复页面/版本/配置/视口五字段唯一，版本/租约/取消发布围栏未删除。没有对开发库执行迁移。旧任务的 protected content、ETag、幂等重放、默认指针及取消/迟到发布回归通过。

删除已作废的取帧 opt-in E2E 和本地 A13 捕获场景；A15 改为独立静态声明、就绪回执与全不透明静态标题。旧 G1/regression 夹具暂直接使用内部播放接口，C2 再切 Scene；历史 G1 结果保留为历史证据，不作为新静态链结论。usePageTimeline、compilePageTimeline、Transport、seek/sampleAt、适配器 applyAt 仍服务交互预览和放映，按 B2/B5 接管后删除。

开发验证：

- `pnpm run test:runtime`：168 文件、1367 项通过、3 项既有跳过；Runtime check/build 通过。
- `pnpm run test:renderer`：53 项通过；`pnpm run test:render-contracts`：40 项通过（两版 DTO/JSON Schema 正反例）。
- Backend 定向：external_screenshot_jobs、page_screenshot、system_timeline_capabilities、static_screenshot_migration、page_screenshot_job_durability、validation_screenshot_publisher、page_screenshot_job_service、page_screenshot_queue_worker、page_screenshot_fingerprint_service、db_adapter_layer、render_motion_dispatch、browser_capture_service，共 74 项通过。
- `test_migration_behavior_contracts.py`：4 项通过、1 项跳过（未配置 PostgreSQL 测试库）。
- `test:editor:check`、`codegen:editor-api`、`test:contracts:generated` 通过；4 个 TypeScript 夹具、A15 Vue 页面和修改过的 MJS 语法通过。

未运行：真实浏览器/Renderer、导出实际产物、PostgreSQL 真实升级、生产镜像、独立产物和长稳；交 C3。未启动应用服务、未重置开发数据。

## B2 第一批：内部会话与假任务（2026-10-29）

基于 B1 `925b3d7`；新增[PageSceneSession](../../../../runtime/src/core/scene/page-scene-session.ts)、宿主 slot、任务图校验、有效经过时钟和释放域。只调度任务起点并聚合实际完成，不对动画/媒体每帧采样。明确 prepare 执行注册、静态创建前拦截、有限/装饰参与方式、失败传播、实际完成依赖、内部冻结、至多一次回调和有界期限；详见[B2 分批实施记录](./work-packages/b2-completion-aggregation.md#分批实施记录)。

开发验证：`pnpm --filter web-runtime-vue exec vitest run src/core/scene`，3 文件 34 项通过；`pnpm --filter web-runtime-vue check` 通过。补测发现并修复了旧清理回调重入切页可覆盖新 generation，以及 Promise 无拒绝原因被误判成功的问题。覆盖快速离页再进入、旧 Promise 成败、重复 stop、逆序清理及迟到释放、准备/完成超时、startMs/真实 afterTrack 延时、资源受阻和宿主冻结合并、ambient 不阻塞、循环/无限前驱拒绝，以及静态零注册。

本批未接公开入口、GSAP、Three.js、真实媒体或 Deck；旧公开播放入口仍由当前宿主使用，B2 后续批次接管后统一删除。B2 保持实施中；本批不重复已通过的 B1 全量 Runtime 回归，不作实机通过结论，真实验收统一 C3。未启动应用服务或迁移开发库。

## B2 第二批：GSAP 正向序列（2026-10-29）

基于 `b707c06`。新增内部 GSAP Scene 任务、受管填充接口、画布目标解析与参数/回调围栏；实际完成、冻结与取消均接入 PageSceneSession，不引入全局采样。支持多序列、DOM/SVG、数值对象、属性和标签/错峰、有限重复与无限装饰；回调在准备时禁用、call 至多一次、onUpdate 正向重复更新。异常回调转任务失败，render 退出后释放；异步回调明确拒绝。填充完成封口，静态入口仍由 slot 在创建前拦截。准备失败现在保留 taskId，并立即清理其余任务。

验证：Scene 4 文件 47 项通过；Runtime check 通过。完整 `pnpm run test:runtime` 首次有一项已有 Mermaid SVG 测量在高并发下超时；定向将该文件与 GSAP 单测一起重跑 20 项通过，再用 `pnpm --filter web-runtime-vue test --maxWorkers=8` 重跑完整集合，172 文件 1414 项通过、3 项既有跳过。未修改 Mermaid 实现或测试时限。真实 GSAP ticker 单测在模块导入前安装同一只假时钟；首次只在 beforeEach 替换时钟时，GSAP 捕获的原 Date.now 未被推进，已修正测试接线后重跑。

尚待公开入口、直接 GSAP/插件导入校验、页级声明与 Deck/预览宿主切换、旧链删除；B2 继续实施中。未运行真实浏览器、Renderer、导出产物或镜像，本批不作视觉验收结论。

## B2 第三批：页级声明与卸载生命周期（2026-10-29）

基于 `b0b3b79`。新增[页级声明登记](../../../../runtime/src/core/scene/page-scene-definition.ts)与内部 Vue 组合式绑定；挂载只登记，宿主 prepare 才执行 define 并登记任务/视觉。每画布只有一个声明，同页多序列由其统一拥有。卸载取消绑定会话，清理先移出发现范围再触发，避免重入或迟到结果复活旧页面；prepare 前失效的根节点明确失败。

接入 B0 受管页面标记，静态执行仍需独立呈现声明；capture/export/thumbnail 下 Scene define、任务启动及 GSAP 构造均为零。尚未增加公开 manifest 项，避免新旧入口并存。

验证：`pnpm --filter web-runtime-vue exec vitest run src/core/scene src/runtime-kit/internal/composables/use-page-scene-definition.test.ts`，6 文件 60 项通过；Runtime check 通过。覆盖真实 Vue 挂载/卸载、跨画布与重复声明、准备中/播放中取消、旧引用失效、静态声明缺失及静态零副作用。完整 Runtime 回归沿用上一批 1414 项通过的记录，本批运行受影响集合；实机、Renderer 与实际产物未运行，统一 C3。公开入口、Deck/预览宿主和旧链删除继续由 B2 后续批次处理。

## B2 第四批：可取消资源等待（2026-10-29）

基于 `12a9d3b`。将视觉资源探测接入统一取消域并拆分图片任务；取消/超时/正常完成后撤销轮询、图片事件、RAF 和未胜出的长计时。原生解码或字体 Promise 的迟到拒绝被消费，不改变页面加载本身。现有 usePlaybackHost 已在停止、切页、换准备和卸载时取消旧探测，为 Scene 宿主复用准备提供基础。

验证：`pnpm --filter web-runtime-vue exec vitest run src/runtime-shell/playback/usePlaybackHost.test.ts src/core/utils/visual-assets.test.ts src/core/utils/visual-assets-cancellation.test.ts src/core/utils/render-ready.test.ts`，4 文件 82 项通过；Runtime check 通过。首轮发现失败页的手动翻页会先建立目标准备，Router 提交时无条件取消导致两个旧回归不通过；调整为只取消不同路径的等待后完整定向重跑通过。覆盖预取消、各图表轮询、图片/背景监听、解码迟到、字体、RAF、正常结束与超时清理，以及宿主停止/切页/卸载后的零启动。未运行实机或实际产物；B2 继续实施中。

## B2 第五批：页面准备屏障（2026-10-29）

基于 `b8d3483`。新增[PageSceneStage](../../../../runtime/src/runtime-shell/playback/page-scene-stage.ts)，沿用 Scene slot 的本地 generation 和取消域，将导航、过渡、DOM、资源与页面/任务 prepare 合并为原有的一次准备期限；不额外创建 Deck 控制器或推进时钟。静态策略直接返回 null；用户显式 start 前没有任务 run。导航失败、画布替换与资源失败返回稳定摘要。

现有 RuntimePageStage 在新过渡开始时撤销旧稳定回执，避免快速往返复用同路径的旧事件；卸载仅清自己的回执，允许过渡层重挂后重新编号。页面根节点发现从原宿主提取共用，现有放映控制器继续提供正式播放，尚未接入临时公共 Scene 入口。

验证：`pnpm --filter web-runtime-vue exec vitest run src/runtime-shell/playback/page-scene-stage.test.ts src/runtime-shell/transitions/RuntimePageStage.test.ts`，2 文件 21 项通过；Runtime check 通过。测试使用真实 Router/Scene，覆盖不合作的旧资源 Promise、快速导航取消、守卫拒绝、准备前后屏障、总期限、静态零导航、空 Scene 与回执所有权。计时器清理断言隔离了导入 GSAP 自带的 ticker，未将动画库的后台句柄误当作 Scene 句柄。

完整 `pnpm --filter web-runtime-vue test --maxWorkers=8`：177 文件、1463 项通过、3 项既有跳过；`pnpm --filter web-runtime-vue build` 通过；`pnpm run test:repository`：8 文件 63 项通过。本次完整集合包含第三至第五批新增用例及既有默认静态截图/导出开发回归。未运行浏览器/Renderer、真实导出产物、生产镜像、独立产物、多窗口或长稳；统一交 C3，B2 保持实施中。

## B2 第六批：公开开发入口（2026-10-30）

基于 `3eb0b74`，按用户要求把旧入口清零与完整验收后移到合并 main 前。新增公开 `usePageScene.v1`，登记 manifest、Backend/Agent 能力目录和公开导入白名单；保留旧入口支持开发分支逐步替换。Vue 生命周期测试迁到公开路径，不重复维护一套私有入口测试。

Vite DEV 挂载后提供 `window.__RUNTIME_SCENE_DEBUG__.play(scope?)/read()/stop()`，复用已有 Scene slot、prepare、GSAP 与任务聚合；导航、卸载、HMR、重复播放和全屏交接释放旧会话。静态上下文与嵌套静态画布不启动；同页旧时间轴冲突明确拒绝。正式放映/Editor 桥仍在 B2/B5 接线，此开发入口不承担自动翻页或生产放映。

验证：Scene、公开入口和 manifest 共 8 文件 93 项通过；Runtime 类型检查与 `pnpm --filter web-runtime-vue build` 通过。Backend manifest/能力目录契约共 16 项通过；根仓 manifest 与文档/技能检查共 9 文件 68 项通过。检索生产 JS，未包含 `installPageSceneDebug` 或调试专用错误码，确认开发执行入口已排除。未重复全量 Runtime 集合，本批运行受影响集合；未启动服务或重置开发库，未运行浏览器/Renderer、真实导出、独立产物或长稳；正式验收继续交 C3。调试步骤见[Scene 开发调试](../../runtime/scene-development.md)。

## B2 第七批：正式 Deck 与宿主（2026-10-30）

基于 `31bfa40`，原控制器就地替换为 DeckPlaybackSession；正式 usePlaybackHost 接入 PageSceneStage，不再构造 PageMediaSession 或寻找旧时间轴句柄。根元素全屏才创建/启动放映，退出、切页、失败和卸载立即释放任务；同一声明跨调试/正式宿主互斥所有权。三种推进、实际完成后停留、末页/循环、保持/释放、内部冻结和迟到计时守卫完成。Runtime 接受 scene_end/completionDelayMs，Backend DTO 与 Editor 配置仍留 B5 同批升级；旧推进方式明确拒绝。

控制条改为保持/释放，不暂停 Scene；演讲交接停止本窗口任务。Presenter 当前协议继续投影页面状态，旧暂停/定位命令明确不可用，不伪装执行；全协议删减交 B5。宿主相关旧时间轴/媒体测试随消费者移除，新增真实 Scene 调度与 Router/Vue 接线回归。

验证：Deck 15 项、宿主/过渡/Scene/公开入口定向 135 项、布局/宿主/观众调用端定向 60 项通过，Runtime check 通过。完整 Runtime 首轮有既有 Mermaid 测量超时及控制条 tooltip/旧 auto 参数断言问题，恢复 tooltip 并更新已变更的参数语义后定向通过；降低到 `pnpm --filter web-runtime-vue test --maxWorkers=4` 完整重跑，177 文件 1420 项通过、3 项既有跳过。未修改 Mermaid 时限。检索正式放映目录无旧控制器、PageMediaSession、PageMotionHandle、sampleAt/seekMotion 有效调用。未运行浏览器/Renderer、实际产物、镜像或长稳；C3 继续承接。

## B2 第八批：正式单页预览（2026-10-30）

基于 `37b1921`。新增 PageScenePreview 与正式 Scene 预览协议，删除旧 motion 预览桥及其轮询/采样命令；开发控制台复用同一执行器。声明目录事件使挂载后可发现但不自动执行，过滤静态缩略图，保持每页单一所有权。父窗口握手固定 origin，所有消息同时验证窗口、版本与字段；unsync、卸载、HMR 和资源准备中的取消均释放任务。

Editor 普通/放大预览共享播放/停止控件；移除进度、定位、暂停、重播和降动效控制。放大前停止原画布，关闭/卸载取消 iframe；completed 仍允许停止 ambient。iframe 消失时发送取消消息的异常被隔离，避免影响组件清理。Backend DTO 与 Presenter 全协议仍归 B5；本批没有引入兼容消息或旧动作映射。

开发验证：Scene/预览/宿主/公开入口 11 文件 136 项通过；Editor 控件与 iframe 消息 8 项通过；协议对拍 2 项通过；Runtime 和 Editor check 通过。完整 Editor 160 文件 913 项通过，Editor build 通过；根仓协议与文档检查 9 文件 65 项通过。`pnpm --filter web-runtime-vue test --maxWorkers=4` 完整回归：177 文件 1428 项通过、3 项既有跳过；真实浏览器、Renderer、发声和产物不在本批执行。

## B2 第九批：GSAP 源码边界（2026-10-30）

基于 `fdbb0e1`。页面和工作空间组件只通过 Scene 受管门面使用 GSAP；直接核心包/插件导入与重导出由 Backend 依赖解析、远程预览和构建/诊断插件拒绝。平台内部 GSAP 实现继续正常解析。生成 Worker 从同一 TS 策略生成纯 JS，Backend 与 Runtime 以共享正反例对拍。策略版本加入 CodeCheck 指纹，防止旧检查通过结果绕过新规则；这不是任意 JS 沙箱。

开发验证：Runtime 导入边界、远程预览和 Worker 三文件 70 项通过，Runtime check 通过；Backend 策略、依赖解析、指纹、缓存与 CodeCheck 五文件 63 项通过。首次新增用例发现原依赖正则未识别副作用导入，修正后全通过；首次 Runtime 共享 fixture 相对路径错误已修正。未运行浏览器或启动服务。下一批补齐正式公开入口样例并关闭 B2 工程出口。

## B2 第十批：样例、冻结边界与工程完成（2026-10-30）

基于 `95309dc`。新增正式公开入口样例与独立 Runtime 路由，涵盖数字、按实际完成依赖的打字机、SVG 描边、多条并行序列、DOM/CSS 无限装饰与有限 Canvas 粒子。Canvas 上下文/RAF 只在任务 run 创建，冻结不计入有效经过，stop/卸载释放且恢复独立 SVG 海报。静态截图、导出和缩略图使用完整模板，不执行 Scene。样例测试挂载真实 Vue 组件并运行真实 GSAP ticker，使用导入前安装的同一只假时钟；这只证明执行、完成与清理，不证明真实像素。

补测覆盖已隐藏时创建会话、freeze 不被 visibility 提前解除、resume 后才执行，以及 manual 的未使用零停留与 timer 零预算拒绝。正式放映、iframe 预览和 DEV 调试使用同样生命周期语义，预览监听归执行器统一释放。首次样例断言只观察了处于错峰平台段的首粒子，改为比较整组粒子后通过，未修改生产动画去迎合断言。

最终开发验证：

- `pnpm --filter web-runtime-vue test --maxWorkers=4`：179 文件 1451 项通过、3 项既有跳过。
- `pnpm --filter web-runtime-vue build`：包含 vue-tsc 检查与生产构建，通过；有既有体积与插件耗时提示。正式样例进入独立 chunk。
- 样例/Scene/公开入口 96 项通过；补充宿主/Deck 29 项、预览/调试/宿主 44 项通过，之后已纳入上述完整 Runtime 回归。
- 第八批完整 Editor 160 文件 913 项、check/build 通过；后续未修改 Editor，无重复执行。
- Backend 第九批策略/依赖/指纹/缓存/CodeCheck 63 项通过；本批静态截图与 Kit 契约 7 项通过。
- 根仓仓库约束、Scene 预览协议、项目模板与 Kit manifest 共 11 文件 72 项通过。

B2 状态改为工程完成；正式宿主与单页预览不再消费旧 Transport/采样/媒体会话。保留的模型、媒体、配置/客户端消费分别交 B3/B4/B5，旧内核/公开入口/剩余 readiness 和浏览器夹具由 C2 全仓清理；责任表见[B2 工程出口](./work-packages/b2-completion-aggregation.md#第十批公开样例与-b2-工程出口2026-10-30)。GB 尚需 B3–B5，C3 实机尚未执行。未启动开发服务、未重置开发数据；未运行真实浏览器、Renderer、实际导出、镜像、独立产物、多窗口、发声、WebGL、长稳及 test:all，这些按当前顺序统一靠后。

## B3：模型正向播放与实例所有权（2026-10-30）

第一批 `a3b6a33` 抽离相机、首帧证明、实例资源与静态采集，第二批进一步拆出 WebGL 生命周期并由实例 Scene 控制器替换 Viewer 的旧姿态采样句柄。新增 AssetModel.v3，移除 v2；每实例独立 Mixer/action，以真实 finished 完成任务，支持有限/无限、实际依赖、冻结、资源替换和离页取消。页面只能修改实例数值副本，不获得共享几何/材质/骨骼。静态帧保持同步重绘/PNG 读回与独立静态初始姿态。

Renderer 采用使用中独占、空闲上限 4 的有界池；明确保留上下文的成本并补 active/idle/创建/销毁计数，决策和 C3 的 A04 观测口径见 [B3](./work-packages/b3-model-forward-playback.md)。不把池计数、模拟 canvas 或 Three.js CPU 动作当成真实 GPU 回收证据。

开发验证：模型/静态帧/资源组件 109 项、manifest 16 项、根仓契约 68 项、Backend Kit 契约 6 项通过；Runtime check/build 通过。完整 Runtime 首轮仅两条仍期待 AssetModel.v2 的断言失败，其余 1457 项通过、3 项跳过；更新后该 manifest 文件 16 项通过，B4/B5 之后再跑最终完整回归。B3 工程完成，真实 WebGL、上下文恢复、PNG 像素、独立产物与 A04 资源曲线统一留 C3。没有启动服务或修改开发数据。

## B4：AudioBus、显式媒体与 cue（2026-10-30）

基础批 `c5d8100` 后，资源组件、Scene、Deck cue 与会话静音统一接入窗口 AudioBus。内容由用户控制，旁白/自动视频由页面显式登记任务，cue 保持 Deck 所有权；没有默认 DOM 认领或独立 cue 静音/许可状态。支持实际 play Promise、ended 完成、受阻本地手势恢复、缓冲与外部冻结、角色失败传播、资源替换和离页清理。新原生调用前执行资格由同一总线判断，隐藏期间的失败请求不占用交互池/节流名额，旧 Promise 不能停止新 cue。

删除 PageMediaSession、AssetAudio/Video.v2 和旧同步 useAudioCue.v1，新增显式 createSceneMediaTask.v1 和 Promise useAudioCue.v2；保留 Audio/Video.v1 的用途与静态/内容展示。当前 Runtime frame 的媒体许可提示直接触发本地重试，不能从父窗口代理手势。Backend 删除 page_narration/audio_cues 功能门、开放集合、写入/披露/快照分支及关闭夹具，API 支持字段固定 true；参数、资源归属与用户权限校验保留，检查缓存使用 audio-bus.v1 执行身份。

开发验证：完整 Runtime 183 文件 1450 项通过、3 项既有跳过；Runtime check/build 通过。Backend 参数、CodeCheck/缓存、Kit、默认开放 API、项目设置、External API、模板导入与预览 109 项通过；根仓音频 fixture、Kit、预览协议与仓库约束 76 项通过。修改 Python 的 F401/F821 检查通过。首轮只发现路由测试旧 config mock 未覆盖 audioConfig、三条已删文件文档链接，以及旧清单断言；修正后复验通过。真实发声、浏览器许可、受保护慢速缓冲、多窗口与镜像/产物均未执行，仍由 C3 验收。B4 工程完成，B5 继续配置、Presenter、AI/CLI 和联合样例。

## B5 第一批：版本化配置与 Editor（2026-10-31）

Backend DTO、Editor 共享放映字段与 Runtime 读取/构建边界同步改为 schema 4。只保留 manual/timer/scene_end、完成后停留与 loop；零停留有效，旧模式与旧字段明确拒绝。Scene capability 取代 timeline。模板包 schema 5，旧包要求重建；迁移只修改新行默认，保留既有 JSON 并在读取时给出稳定 409。

开发回归中的旧 schema 断言已联动更新；UI 架构测试扫描到测试辅助原生控件后，将其移至测试目录，未扩大业务白名单。未启动服务或修改开发数据。后续继续收敛 Presenter、AI/样例与 CLI。

验证：Backend 配置定向 73 项通过（首次模板旧包用例因上传字段错误失败，修正后包含在补充 API/快照/迁移/渲染身份回归 49 项通过、1 项既有跳过）；Editor 6 文件 36 项通过；Runtime 配置 56 项、边界补测 20 项通过、3 项既有跳过。Runtime/Editor check、codegen 与生成契约门禁通过。SQLite 实迁与 PostgreSQL 离线 DDL 已覆盖；真实 PostgreSQL、服务迁移和浏览器留待 C3。

## B5 第二批：Presenter v5（2026-10-31）

删除 v4 的位置、剩余时长、暂停/恢复/定位、会话自动切换与持久化重放。协议只剩 request-state、有限 intent 和观众原子 state；严格校验版本、产物、角色、owner 与修订。新观众接管会停止旧窗口；控制台导航先发意图，收到观众事实后才更新页码和预览。较新状态不能被旧 revision 或旧 owner 覆盖。

控制器按页面映射、即时双通道与协议拆分。控制台不建立播放时钟；观众本地播放/重试、静音按钮允许当前窗口重新尝试许可。删除无消费者的 allowPresenterSync 策略标志。PresenterPageGrid 仍保留真实 Vue 树，性能页数边界交 C3 实测。

验证：Presenter、执行策略、正式 Deck 与主布局 12 文件 79 项通过；Runtime check 通过。包括双通道重复投递、storage 回退、重开对齐、旧 owner 停止及 hold/release 不连跳。均为无浏览器开发回归，正式多窗口与媒体许可仍未执行。

## B5 第三批：AI 规范与联合样例（2026-10-31）

工具规格继续作为目录/披露/操作手册单一事实源；页/组件规范改为 Scene 多序列、显式媒体、模型 v3、cue v2 与独立静态态。删除旧时间轴创作、旧配置和音频阶段门禁建议；强调真实片段索引/签名、单个自动发声主媒体、禁止 GSAP 插件和截图结果区分。

公开 SceneShowcase 可通过真实模型/旁白资源参数启用联合分支，含两个串行动作、旁白和 cue。新样例用真实 Three.js Mixer 发现：上一段 clamp 终态保留权重，导致第二段姿态被平均。已在下一动作开始前释放上一段动作权重，完成到下一段之间仍保留可读终态，离页恢复初始姿态。

AI 目录/工具/业务集成 39 项通过；样例、模型与核心入口 21 项通过；Runtime/Editor build 通过。首次完整 Runtime 1461 项断言通过但核心导出测试的空配置引发未处理拒绝；fixture 已提供 schema 4 并定向通过，完整回归继续执行。无浏览器或服务数据变更。

第三批收口验证：完整 Runtime 185 文件 1461 项通过、3 项既有跳过，无未处理拒绝；完整 Editor 160 文件 904 项通过。根仓 20 文件 129 项契约、生成门禁、Gateway、Backend Kit/CLI Skill 10 项通过。E2E 收集基线同步到 B1 删除任意时刻截图后剩余的 3 项 runtime-heavy；仅执行 --list，不执行浏览器。

## B5 第四批：CLI 与 GB 工程出口（2026-10-31）

CLI 仓库提交 `9f13ca5`，分支 feature/motion-scene-clients。CLI 0.5.0 / Skill 1.5.0 使用新配置、Scene 模型/媒体/cue 指引；删除旧采样参数和音频阶段门禁，静态截图任务返回独立状态及稳定原因码，可按 job_id 继续查询，下载不信任远程 content_url。完整 209 项通过，无跳过；最终边界 45 项通过，包含任务/页面身份和版本负例。wheel/sdist、分发、help、实时主仓 OpenAPI、锁文件离线校验与技能 quick_validate 通过。在线同步遇 PyPI TLS 失败后，沿用现有环境并离线构建成功，产物未发布。

B3/B4/B5 均工程完成，GB 开发出口关闭。MCP 快照/bindings 因 capability/配置升级可能失配，未刷新或测试，按项目边界明确为非阻塞。C1/C2 工程收口与 C3 集中实机仍未执行；未重启开发服务、未修改 .env 或开发数据、未推送远端。Presenter 网格页数性能边界同样交 C3，不将开发替身计入真实多窗口或声音证据。
