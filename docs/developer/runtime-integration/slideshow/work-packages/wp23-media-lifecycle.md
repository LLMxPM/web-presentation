# WP23：活动页媒体注册与生命周期

状态：已完成（2026-10-18）。阶段：M2。主责：Runtime / Runtime Kit 内部渲染器。
上层工作项：R04（播放基础）；详见[模块计划](../runtime.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP14](./wp14-execution-contexts.md)、[WP22](./wp22-media-schema-permissions.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：VideoViewer 的受控实例/事件、当前页原生媒体集合、活动上下文、离场/暂停/恢复及事件清理。
- 交付物：可报告真实 play/pause/ended/error、按 generation 隔离的媒体适配层。
- 提交边界：不包含第三方 iframe、Web Audio 或画布外脚本音频；不额外暴露 shell 公共能力。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：缩略图不抢播；实际元素监听 ended；只恢复本会话暂停的媒体；离场无残留声音；动态替换旧事件失效。
- [x] 验证范围：媒体适配挂载测试、Promise 拒绝、动态 DOM/清理及 Runtime 回归；真实浏览器媒体播放随 WP24/WP30 验收。
- [x] 关联验收：A15、A19、A20；A15 的禁播由会话不创建/allowPlayback=false 覆盖，A19/A20 的真实播放行为待 WP24/WP30。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP23：活动页媒体注册与生命周期`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 适配层：新增 `runtime/src/core/media/page-media-session.ts`，按活动页根节点收集非循环 `audio`/`video`，直接在实际元素监听 `play`/`playing`/`pause`/`ended`/`error`/`loadstart`/`emptied`；动态增删与 `loop` 变化通过 MutationObserver 刷新。
- 状态：快照提供目标集合、`allEnded` 与 `blocked`；`play()` 以 Promise 结果区分真实播放、`NotAllowedError` 阻止和其它媒体错误；`suspend()` 只记录本会话正在播放的目标，`resume()` 只恢复该集合。
- 清理：页面离场、generation 失效或宿主卸载时 `dispose()` 停播并移除监听；旧会话不再上报事件，被移除或改为循环的媒体会停播。
- VideoViewer：暴露 `getMediaElement()` 与 `media-ready`/`media-unmounted`/`media-reset`，并转发原生 `play`/`pause`/`ended`/`error`；未把 shell 控制器或适配层加入公开 Runtime Kit manifest。
- 验证：`pnpm --dir runtime exec ... vitest run src/core/media/page-media-session.test.ts src/runtime-kit/internal/renderers/VideoViewer.events.test.ts` → 10 passed；`pnpm --dir runtime test` → 140 files/1059 passed/3 skipped；`pnpm --dir runtime check` 通过。
- 未运行：真实 Chromium 的媒体播放、`media_end` 等待与跳页行为（WP24/WP30）。
- 产物：`.tmp/wp23/`。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
