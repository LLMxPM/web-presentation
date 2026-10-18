# WP13：项目音频设置与 cue 绑定存储

状态：已实现，待 WP18/WP20 联调。阶段：M2。主责：Backend。

## 前置与输入

前置完成：[WP01](./wp01-contract-fixtures.md)、[WP06](./wp06-m0-integration.md)。

## 修改范围与交付

- 为 `Project.audio_settings_json` 增加严格三段音量设置、历史默认值和 SQLite/PostgreSQL 迁移。
- 新增 `ProjectAudioCueBinding`，包含项目、cue key、audio asset、gain 和唯一约束。
- 项目内部 API 提供读取/更新/清空语义，区分省略、显式空列表和非法部分对象。
- 保存时校验同工作空间、active、type=audio、合法 key 和严格整数；整批更新保持原子性。
- 项目归档不级联资源；本包不下发 Runtime 快照，不做 Editor UI。

## 完成标准

- [x] 新旧项目默认读取一致，迁移和 downgrade/前向兼容策略明确。
- [x] 非 audio、跨 workspace、归档资产、重复/非法 key 和越界 gain 均拒绝且无部分落库。
- [x] 旧客户端省略 audio 字段不会清空已保存设置。
- [x] API、仓储和服务分层符合现有项目设置边界。

## 实施记录（2026-10-18）

- 默认值集中在 `backend/app/core/audio_defaults.py`，模型列保留 Python 与 server default 两份同源常量。
- `20261018_0100_project_audio_settings.py` 增加 `projects.audio_settings_json`、`project_audio_cue_bindings` 及唯一约束；downgrade 删除表与列。
- `ProjectAudioSettingsService` 负责批量读取、整批校验、写入替换、引用摘要与历史空值回退；项目创建/更新只在完整校验通过后写库，跨工作空间移动清空旧 cue。
- `ProjectUpdateRequest.audio_settings` 省略表示保留、完整对象表示替换、显式 `null` 拒绝；空 `cue_bindings` 表示清空。
- 已运行：`uv run --project backend pytest -c backend/pyproject.toml backend/tests/api/test_project_audio_settings.py -q`（4 passed）；同批 WP14 目标测试共 62 passed；`pnpm run codegen:editor-api` 与 `pnpm run test:contracts:generated` 通过。
- 未运行：未在真实 SQLite/PostgreSQL 实例执行 `alembic upgrade/downgrade`；迁移仅为元数据检查与本批 API 测试建表覆盖。Editor UI 与 External API 在 WP18/WP19 验证。

建议提交标题：`WP13：新增项目音频设置与 cue 绑定`。
