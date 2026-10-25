# WP24：媒体结束翻页与受阻恢复

状态：已完成（2026-10-18）。阶段：M2。主责：Runtime。
上层工作项：R04（完成判定）；详见[模块计划](../runtime.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP15](wp15-router-readiness-binding.md)、[WP22](wp22-media-schema-permissions.md)、[WP23](wp23-media-lifecycle.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：状态机媒体等待、多目标完成集合、无媒体延时、循环排除、超时及 blocked/error 恢复命令。
- 交付物：media_end 模式能在真实播放完成后准确推进一次的控制器。
- 提交边界：不把循环背景或用户暂停判为完成，不在此处理跨窗口调度权。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：等待所有参与媒体；无目标走 delay；播放受阻/失败不假装成功；手动跳页取消旧集合；超时有可操作退出。
- [x] 验证范围：虚拟时钟状态机、媒体 Promise/事件 integration、真实单/多视频和失败场景；受阻以注入 `NotAllowedError` 验证，真实有声策略留待 WP30。
- [x] 关联验收：A18、A20 已由真实 Chromium 覆盖；A19 的失效资源与超时为真实场景，受阻为注入拒绝，有声与移动端待 WP30。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP24：媒体结束翻页与受阻恢复`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 配置：`PageAdvanceConfig` 接受 `media_end` 与可选 `mediaTimeoutMs`（默认 300000，范围 1000–3600000）；旧产物缺字段仍回退默认，三种模式都补齐该字段。
- 控制器：`reportReady` 接收参与媒体数；`media_end` 有目标时进入媒体等待并挂超时，无目标按 `delayMs` 停留；新增 `reportMediaEnded`/`reportMediaEmpty`/`reportMediaTargets`/`reportMediaBlocked`/`reportMediaError` 与 `next()`；暂停保留媒体时限，末页不循环停止，单页循环开新 generation 等待宿主重播。
- 宿主：页面就绪后创建媒体会话并按 `play()` Promise 区分成功/阻止/失败；媒体事件与路径/generation 对拍；离场先销毁会话；暂停/恢复走会话 suspend/resume；停止、重试、跳页清理；单页循环新一代重建会话并归零重播。
- 会话：循环背景虽不参与完成集合，但纳入暂停、恢复、动态移除与销毁清理；新增 `restart()` 归零已结束目标。
- 控制条：受阻/错误显示“下一页”；媒体等待显示“媒体播放中/媒体已暂停”和“媒体”剩余文案。
- 自动化：定向 69 passed；`pnpm --dir runtime test` → 140 files/1074 passed/3 skipped；`pnpm --dir runtime check` 与改动文件 ESLint 通过。
- 真实 Chromium（Runtime 7373，临时路由配置拦截）：3 个视频同播（2 目标 + 1 循环背景），暂停 1.2 秒进度漂移 0，结束后自动推进；失效资源真实错误、1 秒超时真实暂停、下一页回到媒体页恢复播放；受阻为注入 `NotAllowedError`（样例视频无音轨，Chromium 默认允许其自动播放）。
- 未运行：有声未静音的真实策略、移动端行内播放、经 Backend 保存 `media_end`（能力开放属 WP30）、跨窗口调度（WP25/WP26）。
- 产物：`.tmp/wp24/`（摘要、测试输出、浏览器截图与 JSON）。
- 提交：`4083bbc`。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
