# WP19：CLI 配置与路由往返

状态：完成（2026-10-17，CLI 仓 `d82bf96`）。阶段：M1。主责：web-presentation-cli。
上层工作项：C02；详见[模块计划](../clients.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP07](wp07-external-api-codegen.md)。
字段与行为以[统一契约](../../../../developer/runtime-integration/slideshow/contract.md)为准；所有依赖编号见[执行清单](README.md)。

## 修改范围与交付

- 修改范围：同步 Client 模型、既有项目/路由命令、结构化输入和 Skill 文档；读取原始覆盖并过滤只读生效值。
- 交付物：CLI 可保存项目默认、逐页覆盖和 null 清除的独立客户端发布。
- 提交边界：在 CLI 仓执行，具体命令名以该仓为准；不改主仓 Runtime fixture。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：改排序不丢参数；旧服务明确不支持；幂等和字段错误透传；保存配置不冒充浏览器已播放。
- [x] 验证范围：CLI 仓序列化/命令/旧服务测试；真实 Gateway 和 Editor 交叉往返。
- [x] 关联验收：A05、A17；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP19：CLI 配置与路由往返`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 新增 `wp project slideshow get/update`：读取项目顶层 `slideshow`；更新接受完整 slideshow 对象或包含 `slideshow` 的对象，只向 `PATCH /api/v1/projects/{id}` 发送放映字段。服务端未返回 `slideshow` 时以 `SLIDESHOW_CAPABILITY_MISSING` 明确失败。
- 新增 `wp project route update`：先读取 route-tree，按完整路径（`cover`、`chapter-1/overview`）应用 `order`、`hidden`、`group_title`、`transition`、`advance`；整树写回时保留未编辑节点的原始覆盖，过滤 `id`、`page_code`、`page_title`、`display_title`、`effective_slideshow`，显式 null 原样发送以恢复继承。未知路由、重复选择、分组级覆盖和旧服务缺字段均在写入前失败。
- Skill 1.3.5：新增放映配置与路由覆盖流程，明确配置保存不等于控制浏览器播放；CLI 帮助与文件参数文档同步。
- 测试：`uv run pytest packages/api-client/tests packages/cli/tests -q` → 103 passed；新增 8 个 CLI 用例覆盖往返、只读过滤、显式 null、未知路由、旧服务、幂等键冲突和帮助注册。
- 真实往返：专属账号项目 119。CLI 写入项目默认（push 600ms、timer 4000ms、loop、auto_start），Editor 内部 API 读取一致；Editor 先为中页设置 fade/timer 5000ms 覆盖，CLI 重排后覆盖保留；CLI 发送 `transition=null`、`advance=null` 后中页恢复继承并返回项目默认生效值。非法 `effect=wipe` 由 Backend 422 透传；复用首个幂等键提交不同合法载荷返回 409 `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`。
- 未运行：旧版真实 Backend 交叉验证（本环境只有当前服务端，旧服务行为由单测覆盖）；PyPI/GitHub 发布由 WP21 或 CLI 仓发布流程处理，本次只提交源码与 Skill。
