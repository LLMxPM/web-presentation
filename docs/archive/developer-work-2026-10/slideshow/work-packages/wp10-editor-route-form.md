# WP10：Editor 逐路由覆盖与映射

状态：完成（2026-10-17）。阶段：M0。主责：Editor。
上层工作项：E02；详见[模块计划](../editor.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP04](wp04-route-overrides-api.md)、[WP07](wp07-external-api-codegen.md)、[WP09](wp09-editor-project-form.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：叶子节点设置面板、继承/覆盖选择、生效摘要与读→草稿→写映射；排序、移动、重命名和取消。
- 交付物：每次页面引用均能配置并恢复继承的路由编辑界面。
- 提交边界：分组不提供放映配置；批量设置留作后续增强。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：null 清除正确；过滤只读字段；显式覆盖不被展开的生效值替代；失败保留整树草稿。
- [x] 验证范围：路由映射及 UI 单测、重复引用、移动/排序回归、键盘和响应式验证。
- [x] 关联验收：A02、A03、A04；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP10：Editor 逐路由覆盖与映射`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 映射：`mapRouteTreeToWriteItems` 只读取 `transition`/`advance` 原始覆盖，忽略 `effective_slideshow`；`cloneProjectRoutes` 与 `normalizeProjectRouteOrders` 保留顶层/子页覆盖，排序、移动和重命名不会静默丢弃。
- UI：新增 `ProjectRouteSlideshowDialog`，按“覆盖动画/覆盖翻页”两组编辑；未勾选提交 null（恢复继承），另提供“恢复继承”一键清除。只在叶子行（顶层页与分组子页）提供入口，分组行不出现；按钮显示“放映”或“放映·自定义”。
- 生效摘要：弹窗展示项目默认值（来自 `ProjectItem.slideshow`），未覆盖时提示继承的具体效果与时长。
- 失败保留：保存仍走整树草稿与既有 `validateProjectRoutes`；接口失败时弹窗不关闭，草稿保留。
- 验证：`npx vitest run src/utils/project-route.test.ts src/components/project/ProjectRouteSlideshowDialog.test.ts` → 10 passed；连同 WP09 相关 19 passed；`npx vue-tsc --noEmit` 通过。
- 未运行：真实浏览器拖拽/键盘操作 E2E（留给 WP12）；批量设置按计划留作后续增强。
