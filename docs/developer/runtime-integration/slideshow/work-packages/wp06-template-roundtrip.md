# WP06：模板包 schema 3 与三版本往返

状态：完成（2026-10-17）。阶段：M0。主责：Backend。
上层工作项：B04；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP03](./wp03-project-settings-api.md)、[WP04](./wp04-route-overrides-api.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：模板项目摘要、project/routes JSON、预检和导入导出；schema 3 写入及 1/2/3 读取。
- 交付物：携带项目默认和路由原始覆盖的可迁移模板包。
- 提交边界：不能因 CURRENT 从 2 变 3 而取消 schema 2 支持；不改组件分享包。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：旧包补默认；新包往返等价；不把生效值存为原始覆盖；只复制页面资源不携带项目路由设置。
- [x] 验证范围：模板格式、预检/正式导入一致性和导出→导入→再导出。
- [x] 关联验收：A01、A06、A08；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP06：模板包 schema 3 与三版本往返`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录

- 版本：`PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION = 3`，新增 `SUPPORTED_PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSIONS = {1,2,3}`；预检不再用 `{1, CURRENT}` 导致 v2 失效。
- 导出：`project/project.json` 增加完整 `slideshow`；`project/routes.json` 叶子增加原始 `transition`/`advance`（继承为 null），不写 `effective_slideshow`；模板项目摘要增加 `slideshow`。
- 导入：schema 3 要求完整可校验 `slideshow`，schema 1/2 缺失补默认值；路由覆盖按整组校验，分组非 null 覆盖报错；生效值只由解析器派生，不落库为原始覆盖。模板预览配置包同步下发 `transitionDefaults`/`playback` 与叶子生效组。
- 页面复制：既有页面复制链路只复制页面资源，不读取路由表，故不携带项目路由设置（无需新增分支）。
- 验证：`pytest tests/api/test_project_template_package_slideshow.py` → 3 passed（schema 3 往返、v1/v2 补默认、schema 3 缺字段拒绝）；`pytest tests/unit/test_project_template_package_service.py tests/unit/test_project_template_package_routes.py tests/api/test_project_template_package_model3d.py` → 5 passed；`pnpm run test:contracts:generated` → 一致。
- 未运行：真实跨工作空间含附件资源的完整模板导入（模型包用例已覆盖资源路径）。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
