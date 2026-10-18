# WP27：Editor 媒体模式配置

状态：已完成（2026-10-18）。阶段：M2。主责：Editor。
上层工作项：E04（表单/提示）；详见[模块计划](../editor.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP09](./wp09-editor-project-form.md)、[WP10](./wp10-editor-route-form.md)、[WP22](./wp22-media-schema-permissions.md)、[WP24](./wp24-media-end-advance.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：生成类型更新、项目/逐页 media_end 和超时字段、无媒体回退说明，以及真实能力控制选项。
- 交付物：能保存并正确说明媒体结束翻页的项目/路由表单。
- 提交边界：不在 Editor 维护播放器或第二份媒体状态，不改变共享样式模型。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：继承/null 和新 advance 完整对象均正确；受阻提示可操作；能力未开放时不提供伪可用选项。
- [x] 验证范围：新字段草稿/映射/转换/能力显示测试及浏览器入口联调。
- [x] 关联验收：A02、A03、A18、A19；见[联调与验收计划](../acceptance.md)。A02/A03 的表单保存与 A18/A19 的受阻提示已覆盖；`media_end` 真实保存随能力开放归 WP30。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP27：Editor 媒体模式配置`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 能力源：新增公开只读 `GET /api/system/slideshow-capabilities`，直接复用 External API 的 `build_slideshow_capabilities()` 与可执行模式常量；外部能力、Editor 表单和写入门禁共用同一份声明。
- Editor：新增 `useSlideshowCapabilities()` 单次缓存读取；项目/路由表单按返回的 `advance_modes` 构建选项，未声明 `media_end` 时不出现该选项或超时字段；能力未开放但草稿含 `media_end` 时提示改用其它模式。
- 媒体字段：`media_end` 下展示“媒体等待上限（秒）”（1000–3600000ms，默认 300000），停留字段改为“无媒体时停留”；补充无媒体回退、循环背景不参与等待，以及浏览器受阻时使用“重试/下一页”的说明。
- 提交语义：项目表单始终提交完整 `SlideshowSettings`；路由覆盖继续按组提交完整对象或 null，`media_timeout_ms` 始终随 `advance` 写入；继承摘要展示媒体结束的等待上限。修正 WP22 遗留的两处项目弹窗测试期望（补充 `media_timeout_ms`）。
- 生成物：运行 `pnpm run codegen:editor-api` 更新 OpenAPI（新增能力端点），`pnpm run test:contracts:generated` 通过。
- 自动化：后端放映相关测试 52 passed；Editor 定向 4 files/19 passed；`pnpm --dir editor test` 153 files/851 passed；`pnpm --dir editor check` 通过。
- 真实 Chromium（Editor 5173 + Backend 8000，专属证据账号与项目）：真实能力返回 schema 2、`advance_modes=["manual","timer"]`，项目与路由表单均只有两种模式且无超时字段；将能力响应模拟为开放后，表单出现“媒体结束”、超时默认 300 秒、无媒体/循环/受阻说明，项目 PATCH 与路由 PUT 载荷均带完整 `{mode, delay_ms, media_timeout_ms}`；真实定时路由保存返回 200 并持久化完整 `advance`。`media_end` 写入仍按门禁返回 422，属 WP30 开放范围。
- 未运行：真实 `media_end` 保存与回读、有声/移动端播放策略、双窗口入口（WP26/WP30）。
- 产物：`.tmp/wp27/`（摘要、测试输出、浏览器截图与 JSON）。
- 提交：待回填。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
