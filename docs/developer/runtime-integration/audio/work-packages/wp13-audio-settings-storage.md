# WP13：项目音频设置与 cue 绑定存储

状态：待实施。阶段：M2。主责：Backend。

## 前置与输入

前置完成：[WP01](./wp01-contract-fixtures.md)、[WP06](./wp06-m0-integration.md)。

## 修改范围与交付

- 为 `Project.audio_settings_json` 增加严格三段音量设置、历史默认值和 SQLite/PostgreSQL 迁移。
- 新增 `ProjectAudioCueBinding`，包含项目、cue key、audio asset、gain 和唯一约束。
- 项目内部 API 提供读取/更新/清空语义，区分省略、显式空列表和非法部分对象。
- 保存时校验同工作空间、active、type=audio、合法 key 和严格整数；整批更新保持原子性。
- 项目归档不级联资源；本包不下发 Runtime 快照，不做 Editor UI。

## 完成标准

- [ ] 新旧项目默认读取一致，迁移和 downgrade/前向兼容策略明确。
- [ ] 非 audio、跨 workspace、归档资产、重复/非法 key 和越界 gain 均拒绝且无部分落库。
- [ ] 旧客户端省略 audio 字段不会清空已保存设置。
- [ ] API、仓储和服务分层符合现有项目设置边界。

建议提交标题：`WP13：新增项目音频设置与 cue 绑定`。
