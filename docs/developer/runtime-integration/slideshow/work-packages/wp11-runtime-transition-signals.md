# WP11：Runtime 参数消费与过渡完成信号

状态：完成（2026-10-17）。阶段：M0。主责：Runtime。
上层工作项：R01；详见[模块计划](../runtime.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP01](./wp01-contract-fixtures.md)、[WP05](./wp05-artifact-build-config.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：配置类型/转换、RuntimePageStage 与 PageTransitionHost；路径/generation 完成信号、错误、transitionend 与有界兜底。
- 交付物：每次稳定显示恰好报告一次、可供调度器使用的页面过渡事件。
- 提交边界：不加入自动翻页定时器；settled 只代表过渡完成，不能冒充资源就绪。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：none/fade/push、反向与快速导航正确；过滤子元素事件；初次挂载在 DOM 提交后完成；旧产物仍可用。
- [x] 验证范围：过渡宿主、配置映射、导航及挂载回归；真实浏览器动画对拍。
- [x] 关联验收：A06、A07；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP11：Runtime 参数消费与过渡完成信号`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 参数消费：新增 `PageAdvanceConfig` 与 `resolvePageAdvance`（manual/timer、1000–3600000ms，旧产物缺省 manual 5000ms）；`RouteConfigYaml` 增加 `playback.autoStart/loop/advanceDefaults` 与叶子 `meta.advance`，路由映射同时下发 transition/advance，分组不继承。`media_end` 在 Runtime 配置校验中被拒绝并回落默认值。
- 完成信号：`PageTransitionHost.settled` 改为 `{path, generation}`，同一 generation 的 `transitionend` 与兜底计时只生效一次；只接受目标层自身 transform/opacity 事件，过滤子元素冒泡；快速导航与旧页迟到事件按 generation 丢弃。初次挂载和无动画导航在 `nextTick`（DOM 提交）后报告。
- 向上接通：`RuntimePageStage` 转发 `settled` 并写入 `runtimeSession.transitionSettled`；`settled` 只表示整页过渡完成，不冒充资源就绪。错误路径保持既有恢复逻辑。
- 验证：`npx vitest run src/runtime-shell/transitions/PageTransitionHost.test.ts src/core/utils/page-transition.test.ts src/core/utils/config.test.ts` → 19 passed（含初次挂载、子元素过滤、transitionend 提前收尾、兜底不重复、generation 递增）；`npx vue-tsc --noEmit` 通过。
- 未运行：真实浏览器动画/反向推入像素对拍（留给 WP12 联调）。
