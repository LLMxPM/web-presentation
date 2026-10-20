# WP05：预览与构建快照下发

状态：完成（2026-10-17）。阶段：M0。主责：Backend / Runtime 构建接入。
上层工作项：B03；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP03](./wp03-project-settings-api.md)、[WP04](./wp04-route-overrides-api.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：ProjectRouteService、ProjectConfigService、ProjectArtifactBuilder 及构建输入；项目默认与叶子生效组的 Runtime 输出和身份摘要。
- 交付物：预览、历史快照和构建产物采用同一份冻结后的放映参数。
- 提交边界：不从 runtime/public/config 读取生产默认，不按停留时间变化强制重截全部页面。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：在线预览和下载构建参数一致；旧窗口/历史不热读新配置；只有实际影响静态渲染的输入触发相关截图指纹变化。
- [x] 验证范围：产物结构契约、预览/构建快照 integration、配置摘要与旧产物兼容。
- [x] 关联验收：A02、A06；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP05：预览与构建快照下发`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录

- 交付代码：`ProjectRouteService.build_runtime_route_config` 输出根级 `transitionDefaults`、`playback`（`autoStart`/`loop`/`advanceDefaults`），每个叶子页 `meta.transition`/`meta.advance` 为 Backend 解析后的完整生效组；`ProjectArtifactBuilder` 的路由工具类型同步放宽。
- 快照语义：预览 artifact 与构建 snapshot 共用 `ProjectArtifactBuilder.build_snapshot` → `config_bundle.routes`，创建时一次性写入 RuntimeArtifactStore；不会热读项目表。项目默认变更不重写路由原始覆盖。
- 截图指纹：未把 `delay_ms`/`loop`/`auto_start` 纳入 `PageScreenshotFingerprintService`，静态截图输入未变化时不触发重截；翻页动画在捕获上下文由 WP14/WP17 禁用。
- 后续收敛（2026-10-20）：路由进入截图身份的方式改为「可达性门控 + 页码目录投影」，见[页面校验截图计划](../../page-validation-screenshot-agent-guidance-plan.md) WP04 条目与 `backend/app/services/page_render_identity.py`。`transition`/`advance`/`playback` 已从身份中彻底剔除，模块入口不渲染的 `app` 展示字段同样不再参与。
- 验证：`pytest tests/api/test_project_preview_slideshow.py` → 2 passed（默认值/生效值下发、旧 artifact 不随 PATCH 变化、新 artifact 使用新值）；`pytest tests/api/catalog/catalog_routes_versioning_cases_1.py` → 16 passed（响应新增字段已更新期望）。未运行真实构建产物对拍（需要完整 Vite 构建链，留给 WP12 联调）。
- 边界：模板包预览配置包未在此包改造，由 WP06 处理。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
