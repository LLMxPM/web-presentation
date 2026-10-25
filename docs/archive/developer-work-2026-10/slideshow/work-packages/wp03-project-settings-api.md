# WP03：项目配置 CRUD 与样式隔离

状态：完成（2026-10-17）。阶段：M0。主责：Backend。
上层工作项：B02（项目接口）；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP01](wp01-contract-fixtures.md)、[WP02](wp02-database-migration.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：项目创建 default/style/custom、PATCH 和详情中的顶层 slideshow；项目服务、响应映射及应用样式路径。
- 交付物：项目默认配置可保存和查询，字段省略、完整替换和非法 null 有明确行为。
- 提交边界：只改内部项目路径；External 适配交给 WP07，逐页覆盖交给 WP04。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：创建省略采用后端默认；PATCH 省略不变；应用/另存样式不修改放映设置；权限检查沿用项目边界。
- [x] 验证范围：项目 API 创建/更新/读取；样式应用隔离、字段错误及工作空间权限。
- [x] 关联验收：A01、A02、A03、A08；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP03：项目配置 CRUD 与样式隔离`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录

- 交付代码：`ProjectCreateRequest.slideshow`（省略取默认完整值）、`ProjectUpdateRequest.slideshow`（省略保留、完整替换、显式 null 422）、`ProjectItem.slideshow`；`ProjectService.create/update/_to_item` 统一走 `normalize/load_slideshow_settings`。
- 样式隔离：应用样式分支仅覆盖展示字段，不触碰 `slideshow_config_json`；新增用例验证应用样式后放映配置不变。
- 生成物：运行 `pnpm run codegen:editor-api`，`ProjectCreateRequest`/`ProjectUpdateRequest`/`ProjectItem` 与 `SlideshowSettings` 类型已同步；`test:contracts:generated` 一致。
- 验证：`pytest tests/api/test_project_slideshow_settings.py` → 6 passed；`pytest tests/api/test_project_updated_at_aggregate.py tests/api/test_project_card_cover.py` → 7 passed；`pnpm run test:contracts:generated` → 一致。未运行完整 API 套件（改动仅新增可选字段与项目服务分支）。
- 边界：未改 External API DTO（WP07）；未实现逐页覆盖（WP04）。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
