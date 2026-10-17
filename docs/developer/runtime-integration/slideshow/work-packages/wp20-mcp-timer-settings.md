# WP20：MCP 配置工具与往返

状态：完成（2026-10-17，MCP 仓 `fb927f2`；真实 Gateway 留待 WP21）。阶段：M1。主责：web-presentation-mcp。
上层工作项：C03；详见[模块计划](../clients.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP07](./wp07-external-api-codegen.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：异步 Client、项目/路由 Tool Schema、Resource/摘要、授权和幂等；完整对象与可空覆盖的模型表达。
- 交付物：MCP 可通过受控 External API 完整读写放映配置的客户端发布。
- 提交边界：不新增浏览器远控协议，不以自由文本配置绕过 DTO。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：Schema 和业务错误与服务端一致；无权工作空间失败；恢复继承发送 null；不回写只读字段。
- [x] 验证范围：MCP 仓协议/序列化/授权测试与真实 Backend 读改写；真实 Gateway 未运行，记入 WP21。
- [x] 关联验收：A05、A17；见[联调与验收计划](../acceptance.md)。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP20：MCP 配置工具与往返`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。

## 实施记录

- 现有 `wp_update_entity`/`wp_get_entity` 按 OpenAPI 透传，无需新增业务 DTO；为 `project.update.configuration` 与 `project.update.route_tree` 增加 guide 语义提示：完整 `slideshow` 对象、`effective_slideshow` 只读、`transition`/`advance` 整组覆盖、显式 null 恢复继承，以及保存配置不等于控制运行中浏览器。未新增浏览器远控协议或自由文本旁路。
- 新增 `tests/contracts/test_slideshow_config.py` 8 项：guide 请求 Schema 含 `slideshow`/可空字段且不含 `effective_slideshow`；未知效果、越界时间、缺字段、只读字段写入前拒绝；路由写入保留 null 并拒绝只读字段；缺 `slideshow` 的旧契约在 HTTP 前失败；真实 SDK 协议往返验证写入幂等键、`X-Workspace-ID`、显式 null 与 `WORKSPACE_FORBIDDEN`。
- 当前 `mcp` 分支生成物尚未合入 WP07 放映 Schema。测试使用 `.tmp/wp20/merged-openapi.json`（运行中 Backend 的放映 Schema + mcp 分支 `x-wp-operation`/媒体响应元数据）执行；在 mcp 基线 artifact 上 8 项显式 skip，不能算作 CI 已开启。合并生成物不是发布产物，mcp 分支合并 WP07 后应以真实生成物重跑。
- 测试：`WP_MCP_BACKEND_OPENAPI=.tmp/wp20/merged-openapi.json uv run pytest tests/contracts/test_slideshow_config.py -q` → 8 passed；`uv run wp-mcp-check-contract --openapi-file .tmp/wp20/merged-openapi.json` → ok，75 bindings/70 routes；全量 `uv run pytest -q` → 310 passed、5 failed、0 skipped（合并生成物）。同 5 项失败在 mcp 基线生成物上复现，属于与放映无关的既有契约漂移（分页边界与编辑/Job Schema），不是本包引入；基线 artifact 下放映用例 8 skipped。
- 真实往返：专属账号工作空间 37、项目 119。MCP 通过真实 SDK ASGI 协议与真实 Backend HTTP 写入项目默认（fade 450ms、timer 6000ms、loop、auto_start）；重排路由为 middle/cover/last 后，中页保留 push 700ms + timer 4200ms 覆盖，首末页覆盖为 null 并返回项目默认生效值；MCP 读取配置与 Backend 独立读取一致；无权工作空间返回 `WORKSPACE_FORBIDDEN`，未发出业务写请求。OAuth 发现/自省/交换与契约文档由受控测试上游提供，委托令牌在测试 transport 内替换为证据 PAT 后访问真实 Backend。
- 未运行：真实 Gateway/Nginx 转发、真实 OAuth 授权服务器与委托交换、旧版真实 Backend（旧契约由单测覆盖）；由 WP21 阶段出口执行并记录。证据位于 `.tmp/wp20/`（合并生成物、`live_mcp.py`、`live/*.json`），验收后清理。
