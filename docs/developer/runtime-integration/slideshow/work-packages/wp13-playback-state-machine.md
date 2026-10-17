# WP13：单窗口放映状态机与时钟

状态：完成（2026-10-17）。阶段：M1。主责：Runtime。
上层工作项：R02（纯调度）；详见[模块计划](../runtime.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP01](./wp01-contract-fixtures.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：独立控制器的状态、一次性计时、剩余毫秒、generation、开始/暂停/继续/停止、末页结束和循环。
- 交付物：不依赖页面 DOM 的可确定性测试的调度核心。
- 提交边界：不在该包绑定 Vue Router、媒体或双窗口，也不开放自动开始入口。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：只有一个推进句柄；旧回调作废；暂停保留剩余时间；手动页等待；单页循环有完整周期。
- [x] 验证范围：虚拟时钟覆盖全部状态迁移、重复命令、边界和资源清理。
- [x] 关联验收：A09、A11、A12、A13；见[联调与验收计划](../acceptance.md)。本包只覆盖纯调度层，真实联调在 WP21。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP13：单窗口放映状态机与时钟`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 交付：[playback-controller.ts](../../../../../runtime/src/runtime-shell/playback/playback-controller.ts) 与虚拟时钟测试 [playback-controller.test.ts](../../../../../runtime/src/runtime-shell/playback/playback-controller.test.ts)。控制器不导入 Vue、Vue Router 或 DOM，仅依赖注入的 `PlaybackClock`、页面目录与导航回调。
- 状态机：`stopped`、`preparing`、`playing`、`paused`、`ended`、`blocked`、`error`；重复开始/暂停/继续/停止/就绪均幂等，错误与受阻可重试并重新等待就绪。
- 时钟与句柄：`performance.now()` 单调计时，任意时刻最多一个 `setTimeout` 句柄；暂停保存剩余毫秒，继续按剩余时间补足，不做固定 interval 累计。
- generation：开始、停止、页面切换、失败与单页循环都会递增；就绪/错误/受阻信号必须同时匹配路径与 generation，旧计时与旧导航 Promise 的迟到回调被丢弃。
- 页面语义：同路径查询参数变化不重置计时；隐藏页在构造目录时过滤；手动模式页保持 `playing` 但不创建计时；播放中手动跳页回到 `preparing`，暂停中跳页保持暂停并为新页重置完整周期；停止/结束后当前页就绪状态保留，重新开始只重置停留时钟。
- 边界：末页且不循环进入 `ended`；多页循环调用导航回到第一个可见页；单页循环不产生路由切换，但每轮重新建立完整停留周期；路径不在可见目录时不自动推进。
- 验证：`pnpm --dir runtime run check` 通过；专项 `vitest run src/runtime-shell/playback/playback-controller.test.ts` 20 passed；eslint 通过；Runtime 全量 130 个文件中仅既有 `runtime-diagnostics-workspace-pool.test.ts` 出现一次 5s 并发超时，单独重跑 4 passed（1000 passed / 3 skipped）。证据保存在 `.tmp/wp13/`。
- 未运行项：Router/DOM 就绪桥接与真实过渡信号（WP15）、入口控制条与可见性（WP16）、真实浏览器 A09/A11/A12/A13 联调（WP21）、媒体与双窗口（M2）。本包未开放自动开始入口，也未改变当前能力声明。
