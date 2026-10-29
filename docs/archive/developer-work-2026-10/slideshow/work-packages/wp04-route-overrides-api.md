# WP04：路由覆盖、继承与旧树保留

状态：完成（2026-10-17）。阶段：M0。主责：Backend。
上层工作项：B02（路由接口）；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP01](wp01-contract-fixtures.md)、[WP02](wp02-database-migration.md)、[WP03](wp03-project-settings-api.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：叶子路由写入、响应生效值和统一继承解析；整树替换前按完整路径＋页面绑定保留旧覆盖。
- 交付物：可独立设置逐页动画/翻页，并可显式清除单组覆盖的路由 API。
- 提交边界：不依赖重建后的路由 ID 识别旧节点；只读 effective_slideshow 不可回写。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：省略与 null 不混淆；排序不丢覆盖；移动/重命名按契约携带配置；分组非法设置整树拒绝；同页重复引用独立。
- [x] 验证范围：路由服务/API、整树事务回滚、旧客户端省略字段、重复引用和权限。
- [x] 关联验收：A02、A03、A04、A05；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP04：路由覆盖、继承与旧树保留`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录

- 交付代码：`ProjectRouteChildWrite/ProjectRouteItemWrite` 增加 `transition`/`advance`（完整组或 null）；`ProjectRouteChildItem/ProjectRouteTreeItem` 返回原始覆盖与只读 `effective_slideshow`。分组节点非 null 覆盖在校验层直接拒绝。
- 继承语义：字段出现在 `model_fields_set` 时写入（null 清除、对象整组替换）；省略时按“完整路径＋页面绑定”从重建前的旧树快照保留；新节点或无匹配节点继承项目默认值。删旧树前读取覆盖，不依赖旧路由 ID。
- 事务：任何节点参数非法在 `_validate_write_payload` 阶段 422，旧树与覆盖保持不变（由用例断言）。
- 验证：`pytest tests/api/test_project_route_slideshow.py` → 5 passed（原始/生效值、旧客户端排序保留、显式 null 清除、整树拒绝、同页重复引用独立）；`pnpm run test:contracts:generated` → 一致（生成 schema 已重新生成）。
- 未运行：完整路由树 E2E（无既有用例）；Runtime 消费在 WP05/WP11 验证。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
