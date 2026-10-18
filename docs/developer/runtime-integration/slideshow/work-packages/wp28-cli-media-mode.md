# WP28：CLI 媒体模式扩展

状态：已完成（2026-10-18，web-presentation-cli `624ea31`）。阶段：M2。主责：web-presentation-cli。
上层工作项：C04（CLI）；详见[模块计划](../clients.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP19](./wp19-cli-timer-settings.md)、[WP22](./wp22-media-schema-permissions.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：schema 2 能力检测、media_end/超时字段完整往返、结构化输入及 Skill 示例。
- 交付物：可按服务端能力配置媒体模式的 CLI 兼容版本。
- 提交边界：不把 CLI 保存成功描述成有声媒体已获浏览器许可。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：M1 服务不收到未知扩展；未知模式不静默改成 timer；改排序保留新版 advance 对象。
- [x] 验证范围：CLI schema 1/2 序列化、能力负例通过；真实 media_end API 往返待 WP30 能力开放后执行。
- [x] 关联验收：A17、A18、A19 的 CLI 配置侧；真实播放仍由 Runtime/WP30 验收。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP28：CLI 媒体模式扩展`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 校验：新增 `validate_advance_config`，只接受 manual/timer/media_end，校验 delay_ms 与 media_timeout_ms 类型；未知模式返回 `SLIDESHOW_ADVANCE_MODE_UNKNOWN`，不再静默按原样透传。
- 能力：写到 media_end 或 media_timeout_ms 前读取项目工作空间的 `slideshow` capability；未声明 media_end 或 Schema < 2 时返回 `SLIDESHOW_MEDIA_CAPABILITY_MISSING`，PATCH/PUT 均不发送。
- 往返：项目默认与路由编辑都保留完整 schema 2 对象；仅重排序时不额外请求能力，未编辑节点的媒体覆盖原样写回。
- 文档：Skill 补充字段范围、media_end 示例、循环媒体语义与“保存不等于浏览器已播放”。
- 验证：CLI 定向 15 passed；CLI 仓全量 110 passed。
- 未运行：真实 Backend 的 media_end 写入往返（capability 未开放，WP30 复验）；未使用本地账号做真实能力读取，避免改动开发库。
- 产物：CLI 仓 `.tmp/wp28/`。
- 提交：`624ea31`（web-presentation-cli）。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
