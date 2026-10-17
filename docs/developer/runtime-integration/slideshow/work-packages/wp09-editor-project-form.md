# WP09：Editor 项目放映表单

状态：完成（2026-10-17）。阶段：M0。主责：Editor。
上层工作项：E01；详见[模块计划](../editor.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP03](./wp03-project-settings-api.md)、[WP07](./wp07-external-api-codegen.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：专用放映字段组件、草稿组合逻辑、项目入口与顶层 slideshow 提交；秒/毫秒转换和保存错误。
- 交付物：可保存、重开、恢复当前值的项目默认配置界面。
- 提交边界：不继续把全部逻辑堆进展示配置弹窗，不用 localStorage 保存第二份项目配置。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：使用生成类型；应用样式不污染放映草稿；只展示实际阶段可用操作；无动画提交合法 0ms。
- [x] 验证范围：表单草稿/转换/校验/失败保留；Editor 类型检查与相关构建检查。
- [x] 关联验收：A02、A03、A08；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP09：Editor 项目放映表单`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 交付代码：新增 `ProjectSlideshowFields.vue`（效果、动画时长、翻页模式、停留时长、循环、自动开始）与 `project-slideshow-values.ts`（秒/毫秒转换、范围收敛、无动画 0ms）；`src/types/api.ts` 增加 `SlideshowSettings` 生成类型别名。
- 弹窗集成：`ProjectPresentationConfigDialog` 保存载荷增加完整 `slideshow`；应用样式只覆盖展示字段、不重建放映草稿；恢复当前值重新读项目配置。`PagesView` 与 `api/catalog.ts` 的更新参数透传 `slideshow`。
- 阶段边界：UI 只提供 none/fade/push 与 manual/timer，不暴露 `media_end`；timer/auto_start 的配置可先保存，实际执行依赖 WP13–WP16 运行时能力开放。
- 验证：`npx vitest run src/components/project/project-slideshow-values.test.ts src/components/project/ProjectSlideshowFields.test.ts src/components/project/ProjectPresentationConfigDialog.test.ts` → 9 passed（转换/收敛、表单事件、保存载荷与样式隔离）；`npx vue-tsc --noEmit -p tsconfig.json` 通过。
- 未运行：真实浏览器 UI 交互与构建产物验证（留给 WP12 联调）。
