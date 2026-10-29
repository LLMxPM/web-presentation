# WP08：内容助手参数贯通

状态：完成（2026-10-17）。阶段：M0。主责：Backend / AI 工具。
上层工作项：B05（AI）；详见[模块计划](../backend.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP03](wp03-project-settings-api.md)、[WP04](wp04-route-overrides-api.md)、[WP07](wp07-external-api-codegen.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：检查并调整现有项目/路由写工具的白名单、参数、序列化、指南及返回摘要；从 tool_specs.py 派生披露。
- 交付物：现有内容助手能通过受控业务接口保存放映参数的工具说明和实现。
- 提交边界：不新增远程浏览器控制工具，不在工具实现绕过 DTO 直接写数据库。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：工具与 HTTP 对同输入同结果；继承/null 不丢失；未实现的模式不披露；参数失败不会部分落库。
- [x] 验证范围：工具规格/披露防漂移、业务服务复用和权限测试。
- [x] 关联验收：A03、A05；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP08：内容助手参数贯通`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 交付代码：`ProjectCreatePayload.slideshow`（可选完整对象）；新增 `ProjectSlideshowPayload` 与 `project.update.slideshow` action，复用 `ProjectUpdateRequest`/`ProjectCreateRequest` 校验与落库；`update_entity` action 枚举同步扩展。
- 工具规格：`tool_specs.py` 新增放映操作手册（范围、完整对象、`media_end` 未开放、只影响默认值），项目创建手册补充省略默认值说明；路由树手册说明逐页覆盖省略/null 语义。规格由 `tool_specs.py` 单点派生，未另建清单。
- 不披露：guide Schema 中 `advance.mode` 只有 manual/timer，`media_end` 不出现；非法模式在工具参数校验阶段转 `AI_OPERATION_ARGUMENTS_INVALID`，不会部分落库。
- 验证：`pytest tests/integration/ai/test_ai_generic_business_tools.py` → 11 passed（含工具写入、非法 media_end 不落库、创建透传）；`pytest tests/unit/test_generic_business_tools.py tests/unit/test_unified_tool_specs.py` → 24 passed（动作集合与 Schema 防漂移）。
- 未运行：真实模型会话端到端（工具层与 HTTP 服务复用已覆盖）。
