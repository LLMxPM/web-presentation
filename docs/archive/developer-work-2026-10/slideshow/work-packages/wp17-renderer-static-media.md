# WP17：Renderer 禁推进与媒体静态帧

状态：完成（2026-10-17）。阶段：M1。主责：Renderer / 渲染契约 / Runtime 捕获。
上层工作项：G01（探针）、G02；详见[模块计划](../renderer.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP05](wp05-artifact-build-config.md)、[WP14](wp14-execution-contexts.md)、[WP15](wp15-router-readiness-binding.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：render-ready 前验证静态策略与目标路由；视频 poster/有界首帧、静态失败结果，必要时同步纯渲染契约。
- 交付物：自动开始和循环配置下仍能稳定取得正确路由实际 PNG 的捕获链路。
- 提交边界：无必要不升渲染协议；Backend 不启动浏览器，Renderer 不读取业务数据库。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：CSS 冻结、视频停播和业务定时器分别处理；不触发频道同步；认证/期限/产物身份不变。
- [x] 验证范围：Renderer 单测、适用渲染契约往返、真实 Backend→Renderer→Runtime PNG E2E。
- [x] 关联验收：A15、A16；见[联调与验收计划](../acceptance.md)。本包完成静态捕获侧；A16 的 PDF/PPTX/打印导出仍由 WP18 完成。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP17：Renderer 禁推进与媒体静态帧`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 捕获上下文：Backend 对 `page.capture`/`page.diagnose` 的导航地址固定追加 `runtimeCapture=1`，组件诊断保持交互预览语义；Runtime 把查询串中的捕获标记带入 hash 入口导航，项目壳据此切换到 `RuntimeCaptureLayout`，不再先渲染普通布局。
- 协议桥：[render-ready](../../../../../runtime/src/core/utils/render-ready.ts) 增加 `executionContext`、`entryPath`、`routePath`。Renderer 的 [render_ready.py](../../../../../renderer/wp_renderer/engine/render_ready.py) 要求页面操作桥必须为 `capture`、存在稳定路由且与入口一致；桥缺失或不匹配按 `RENDER_ASSET_NOT_READY` 失败，避免旧 Runtime 静默按普通放映截图。
- 静态媒体：[static_media.py](../../../../../renderer/wp_renderer/engine/static_media.py) 在截图前确认目标路由只保留一个可见页面层（项目路由画布或单页 module 预览），暂停全部原生媒体；有 poster 的视频重置 `preload` 并回到海报状态，无 poster 的视频在有界 3s 内等待可用首帧，失败返回可诊断错误而不等待播放结束。
- 动画与定时器：捕获上下文从初始化即禁止自动开始、自动翻页和媒体自动播放；CSS 有限动画由既有视觉资源等待与 Playwright `animations="disabled"` 冻结，未新增第二套动画系统。未触发演讲频道同步。
- 协议：`render-ready.v1` 的 JS 桥字段为增量扩展，`packages/render-contracts` 的请求/回执 Schema 未变，无需版本升级。
- 修复：真实链路暴露出三类问题并已修正：导航地址未携带捕获标记、查询串捕获标记未进入 hash 路由、单页 module 预览没有 `.runtime-page-print-source` 根节点；另修正 Chromium 预加载首帧会隐藏 poster 的行为。
- 验证：`pnpm run test:renderer` 36 passed；`pnpm run test:render-contracts` 22 passed；`pnpm run test:runtime:gate` 通过（138 files / 1044 passed / 3 skipped，构建通过）；`pnpm run test:backend:unit` 通过（878 passed / 674 deselected，含新增导航捕获用例）。证据保存在 `.tmp/wp17/`。
- 真实链路：项目 117 使用 `auto_start=true`、停留 1000ms、`loop=true`。经 Backend `RenderDomainFacade` → Renderer → Runtime 捕获 `/cover` 与 `/frame` 两个不可变快照：封面海报区 98% 为 poster 红色、CSS 动画最终态 95.1% 为绿色、底部中央为页面白色（无控制条）；无 poster 视频区首帧非纯色（均值 115/99/64，标准差 50/48/45）；两张 PNG 均为 1920×1080，且未因自动开始/循环跳页。公开页面截图接口也成功产出 1920×1080 PNG。
- 未运行项：PDF、PPTX、浏览器打印与离屏采集隔离由 WP18 完成；媒体结束翻页与双屏同步属于 M2（WP24–WP26）；完整 M1 能力开放由 WP21 决定。
