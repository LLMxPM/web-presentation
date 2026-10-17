# WP07：External API、能力自省与类型生成

状态：完成（2026-10-17）。阶段：M0。主责：Backend / API 契约。
上层工作项：B05（External/生成类型）、C01；详见[模块计划](../clients.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP03](./wp03-project-settings-api.md)、[WP04](./wp04-route-overrides-api.md)、[WP05](./wp05-artifact-build-config.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：外部项目创建/PATCH/configuration/route-tree，幂等指纹、capabilities.slideshow、OpenAPI 和 Editor 生成类型。
- 交付物：内部与外部一致的配置接口、M0 能力声明、真实 Gateway 样例和生成模型。
- 提交边界：源码 standards 不复制放映 Schema；不实现 CLI/MCP 命令，也不提前声明 timer/media_end 已可执行。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：幂等区分省略/null；configuration 顶层字段位置正确；M0 只声明动画和 manual；无权访问失败。
- [x] 验证范围：External API/幂等测试；codegen:editor-api 后 test:contracts:generated；按技能补真实 Gateway 契约。
- [x] 关联验收：A03、A05、A06；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP07：External API、能力自省与类型生成`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- External DTO：创建请求新增顶层 `slideshow`（省略取默认）；PATCH 复用 `ProjectUpdateRequest`；`PUT /configuration` 新增顶层 `slideshow`（不塞进 `configuration.presentation`，嵌套传入 422）；`GET /configuration` 返回并列 `slideshow`。仅更新 slideshow 时不再构造空展示配置补丁。
- 幂等：创建、PATCH、configuration PUT、route-tree PUT 的指纹改用 `model_dump(exclude_unset=True)`，区分“省略”和“显式 null”；相同键配合不同放映参数或路由覆盖写回语义时返回 409 `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`。
- 能力自省：`GET /api/v1/workspaces/{id}/capabilities` 新增严格类型 `slideshow`；M0 声明 `none/fade/push` + `manual`，三个 auto_play 能力均 false，范围 100–2000ms / 1000–3600000ms。
- 生成类型：运行 `pnpm run codegen:editor-api` → 351 schemas；`test:contracts:generated` 一致。
- 验证：`pytest tests/api/test_external_project_slideshow.py` → 5 passed；`pytest tests/api/test_external_api_v1.py tests/api/test_external_contract_gaps.py` → 25 passed（含既有扁平配置兼容）。
- 未运行：`pnpm run test:contracts:gateway`（需要真实 Gateway 运行环境）；未实现 CLI/MCP 命令（WP19/WP20）。
