# WP14：放映与静态执行上下文

状态：完成（2026-10-17）。阶段：M1。主责：Runtime / Renderer 接入。
上层工作项：R03（上下文）、G01（策略）；详见[模块计划](../renderer.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP11](wp11-runtime-transition-signals.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：定义主画布、交互预览、缩略图、捕获和导出策略，并在宿主初始化前传播；接入原生媒体基础禁播守卫，以及放映暂停时记录正在播放的媒体、继续时按记录恢复的基础能力。
- 交付物：供调度器、媒体、Renderer 和导出共享的内部执行策略接口及基础媒体守卫；M1 的真实页面预览不能仅靠 inert 禁止抢播。
- 提交边界：先交付上下文接口；实际静态媒体与导出接入分别由 WP17/WP18 实现。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：capture/export/缩略图的禁自动策略高于项目 auto_start；不从频道恢复捕获状态；inert 不充当禁播实现。
- [x] 验证范围：各宿主上下文传播、优先级和禁自动挂载测试。
- [x] 关联验收：A14、A15、A16；见[联调与验收计划](../acceptance.md)。真实 Renderer/导出与浏览器证据由 WP17、WP18、WP21 补齐。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP14：放映与静态执行上下文`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 交付三个内部模块：
  - [execution-policy.ts](../../../../../runtime/src/core/execution/execution-policy.ts)：`presentation`、`interactive-preview`、`thumbnail`、`capture`、`export` 五类策略与优先级解析、只收紧不放宽的合并、`auto_start`/自动翻页判定、媒体三档模式（allow/gesture/block）。
  - [execution-scope.ts](../../../../../runtime/src/core/execution/execution-scope.ts)：初始化前写入全局策略，Vue provide/inject 传播，宿主根节点输出 `data-runtime-execution` 与 `data-runtime-media`。
  - [media-playback-guard.ts](../../../../../runtime/src/core/execution/media-playback-guard.ts)：文档级 `play` 捕获守卫（不依赖 inert）与会话媒体协调器；协调器只记录并恢复暂停前正在播放的媒体。
- 优先级：内部 `runtimeExecution` > `runtimeCapture=1` > 单页/组件/资源/模块预览 > `runtimeMode=cards|presenter` > 普通主画布；`runtimeMode=display` 保持 presentation。解析不读取 `channel`，捕获页面无法从演讲频道恢复状态。
- 初始化：[main.ts](../../../../../runtime/src/main.ts) 在配置、路由和组件挂载前初始化策略并安装媒体守卫。
- 宿主接线：捕获布局、普通布局（卡片模式动态收紧）、单页预览、组件预览、资源预览、演讲者控制台、观众窗口，以及 `ViewPreview`（默认 thumbnail，单页预览显式 interactive）。
- 验证：执行上下文专项 5 个文件 26 passed（策略 9、作用域 4、守卫 5、协调器 5、真实宿主挂载 3）；`pnpm --dir runtime run check` 与 `pnpm run test:runtime:gate` 的构建阶段通过；全量 135 个文件 1027 passed / 3 skipped。首次全量中既有 `runtime-diagnostics-workspace-pool.test.ts` 再次出现 5s 并发超时，单独重跑 4 passed，第二次全量全绿。证据保存在 `.tmp/wp14/`。
- 未运行项：Renderer 截图入口与离屏 PDF/PPTX 的静态媒体策略、导出隔离（WP17/WP18）；真实浏览器自动播放/捕获验收（WP21、WP30）；协调器接入放映暂停/继续（WP16）；媒体结束模式（M2）。
- 说明：导出现在仍复用 `runtimeCapture=1` 的 capture 策略，`export` 已可作为显式上下文解析；两者都是全禁播静态策略，具体区分与接入由 WP18 完成。
