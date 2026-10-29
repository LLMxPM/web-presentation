# Motion 收敛开发记录

本记录承接[工作包清单](./work-packages/README.md)。实机、生产镜像、独立产物和长稳证据由 C3 统一取得，工程完成不代表实机通过。

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
