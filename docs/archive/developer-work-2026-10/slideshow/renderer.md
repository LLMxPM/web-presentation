# Renderer、渲染契约与导出实施计划

状态：WP14 已定义 Runtime 执行上下文与基础媒体守卫（2026-10-17）；WP17 已接入 Renderer 捕获上下文、目标路由核对与视频静态帧（2026-10-17）；WP18 已完成 PDF、PPTX 与打印的离屏导出隔离（2026-10-17）；WP30 已完成媒体/双屏下的截图、取消、期限与进程/产物清理回归（2026-10-18）。本模块配合[自动放映总计划](README.md)，保证自动放映不会改变截图、诊断、PDF 或 PPTX 静态采集目标。

实施拆分见[工作包执行清单](work-packages/README.md)：WP14 定义静态执行策略，WP15 接入稳定页，WP17 完成 Renderer 与静态媒体，WP18 隔离导出，WP30 复核媒体/双屏下的生命周期。以下 G 编号保留为上层职责。

## 1. 目标与现状

Renderer 继续只执行受信渲染请求，不管理项目配置、不连接业务数据库。`packages/render-contracts` 继续只定义协议，不加入播放器或浏览器逻辑。

当前 [RuntimeCaptureLayout.vue](../../../../runtime/src/runtime-shell/transitions/RuntimeCaptureLayout.vue) 禁用整页过渡；[Renderer executor](../../../../renderer/wp_renderer/engine/executor.py) 截图使用 `animations="disabled"`；[render-ready 探针](../../../../renderer/wp_renderer/engine/render_ready.py) 等待宿主与视觉资源。这些措施尚不能禁止未来加入的自动翻页定时器或视频原生自动播放。

## 2. 工作包

### G01：统一静态执行上下文（M1，依赖 R01/R03）

- [x] 与 Runtime 定义捕获和导出上下文优先级：禁止自动开始、自动翻页、演讲同步和媒体播放，即使项目 `auto_start=true`。
- [x] 同时检查 Renderer 截图入口、单页/历史版本预览、组件/资源预览、浏览器打印、离屏 PDF/PPTX 采集入口，不只覆盖整项目捕获布局。
  Renderer 截图与 Runtime 预览入口已由 WP17 覆盖；浏览器打印、离屏 PDF/PPTX 采集由 WP18 核查；WP30 复核媒体模式下截图仍为暂停首帧。
- [x] render-ready 前确认目标路由已稳定、只保留目标内容层、放映调度已禁用；先固定上下文再加载页面，避免先播放再暂停的竞态。
- [x] 捕获页面只呈现本次请求的路径和 artifact 身份；不从 BroadcastChannel/localStorage 恢复普通放映状态。

WP14 已交付 Runtime 侧策略、宿主传播与媒体守卫；WP17 已把捕获标记写入 Renderer 导航地址，Runtime 将其带入 hash 路由并上报执行上下文/入口/目标路由，Renderer 在 render-ready 后硬核对。真实 PNG 证据见 [WP17 实施记录](work-packages/wp17-renderer-static-media.md)。

验收：极短停留时间、循环和自动开始都不能使截图翻页或触发窗口同步。

### G02：媒体静态策略与协议核查（M1，依赖 G01）

- [x] 视频优先使用有效 poster；无 poster 时在有界等待后采集可用首帧，全程不依赖实际有声播放。
- [x] 冻结 CSS 动画、视频和播放器定时器分别处理；动态可视资源沿用现有就绪与静态采集能力。
- [x] 缺失媒体或首帧超时按现有错误契约返回可诊断结果，不无限等待播放结束。
- [x] 首先复用现有 render-ready、入场票据和错误结构；只有确实需要新增请求/回执字段时才修改 `packages/render-contracts`。
- [x] 若协议变化，同步 Python DTO、JSON Schema、Backend 协调器和 Renderer 往返测试；保持纯契约包无 Backend/Runtime/Playwright 依赖。

WP17 未修改 `packages/render-contracts`；render-ready 桥以增量字段暴露执行上下文与路由，Renderer 在既有 `RENDER_ASSET_NOT_READY` 错误结构内返回静态失败。

验收：请求与回执身份一致，静态页面与视频页均能得到实际 PNG，未授权素材仍按既有鉴权失败。

### G03：Runtime 导出隔离（M1，依赖 G01/G02）

- [x] 核查 [OffscreenPageStage.ts](../../../../runtime/src/core/services/export/OffscreenPageStage.ts)、PDF、打印与 PPTX 页面采集，把导出上下文传入所有离屏页面。
- [x] 优先使用独立静态舞台，避免导出过程导航正在放映的主画布；如某入口必须暂停主画布，在 finally 中按用户实际意图恢复，不能覆盖用户中途停止。
- [x] 导出异常、取消和超时清理隔离舞台、媒体句柄和监听；主放映页码与剩余时间不得被导出任务污染。
- [x] 保护原有图元、表格和媒体导出规则；本期不把网页翻页动画或自动翻页设置写成 PPTX 原生动画。

验收：放映中导出当前页/全部页，产物顺序、页数和内容正确；导出取消不会留下后台播放或改变主窗口页面。

WP18 已把 `runtimeCapture=1` 同时写入离屏 iframe 的 search 与 hash，打印全部页改为逐页离屏采集，PDF/打印补齐取消信号与 `finally` 清理。真实 PDF/PPTX/打印产物与主画布状态证据见 [WP18 实施记录](work-packages/wp18-export-isolation.md)；媒体结束与双屏回归仍由 G04 在 M2 覆盖。

### G04：媒体及生命周期回归（M2，依赖 R04/R05）

- [x] 自动放映、媒体结束模式、双窗口开启后复跑远程截图、取消、期限、失败重试和产物提升回归（WP30，2026-10-18）。
- [x] 验证每 attempt 仍新建 Chromium/Context；不复用浏览器、不直接 cancel Playwright asyncio Task（WP30 观察 `busy` 时 1 个 Node + 4 个 `chrome-headless-shell` 后代进程，结束后归零）。
- [x] 检查存活/僵尸进程、临时文件、槽位和捕获页面媒体句柄，确认取消和超时均可回收（WP30：取消任务 `cancelled`、期限任务 `RENDER_ASSET_NOT_READY` 后槽位 `idle`、后代进程与工作区文件清零）。

验收：放映功能没有改变 Renderer 单槽、认证、期限和清理边界。

## 3. 验证与交付

模块单测覆盖禁自动上下文和失败路径；真实 PNG、导出文件和浏览器进程清理需要集成/E2E 证据。协议未变更时不为本功能引入无必要的协议版本升级；发生变更时执行渲染契约与 Renderer 配套测试，真实链路按 [dev-start-test 测试矩阵](../../../../.agents/skills/dev-start-test/references/testing-matrix.md)准备。

构建镜像与生产依赖裁剪后的真实启动按对应实现范围验收，不能以组件单测替代。完整跨模块场景见[验收计划](acceptance.md)。
