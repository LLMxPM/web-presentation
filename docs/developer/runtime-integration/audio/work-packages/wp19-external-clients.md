# WP19：External API、CLI 与 MCP

状态：主仓 External API 已实现；CLI/MCP 待各自仓库交付。阶段：M2。主责：Backend / `web-presentation-cli` / `web-presentation-mcp`。

## 前置与输入

前置完成：[WP13](./wp13-audio-settings-storage.md)、[WP14](./wp14-cue-snapshot-packages.md)。

## 修改范围与交付

- 主仓 External API 暴露 audio 上传/查询/替换和项目音量/cue 读取更新，补 scope、幂等、错误及 capability。
- 运行 Editor API codegen 和契约防漂移，更新 External API 参考文档。
- CLI 增加 `--type audio`、项目音频配置读写、清空和可读输出；不返回持久私有 URL。
- MCP 增加异步客户端与严格工具 Schema，资产和绑定返回 ID、逻辑名、类型及摘要。
- 三个仓分别记录测试和版本；允许分步交付，但 M2 出口必须明确未完成消费者的发布限制。

## 完成标准

- [x] 同幂等键同载荷回放不重复写，异载荷冲突。
- [x] 省略、空列表、非法 key、跨 workspace 和非 audio 错误语义在主仓 External API 已覆盖（CLI/MCP 待交付后对拍）。
- [ ] CLI/MCP 能完成上传→绑定→查询→替换→清空真实流程。
- [ ] 独立仓文档、Skill/工具说明和构建分发测试同步。

## 实施记录（2026-10-18）

- audio 复用 External 资源接口：`POST /api/v1/assets`（`asset_type=audio`）、`GET /api/v1/assets?asset_type=audio`、`GET /api/v1/assets/{id}/file` 与带基线/幂等键的 `POST /{id}/replace`；没有新增专用上传路径。
- `GET/PUT /api/v1/projects/{project_id}/configuration` 增加 `audio_settings`；读取绑定附带 `asset_id`、`asset_name`、`asset_type`、`asset_status` 和 gain，写入只接受 ID。`ProjectItem` 继续以 ID 形式返回设置。
- 创建项目支持 `audio_settings`；PATCH 更新沿用内部省略语义。显式 null、部分对象、重复 key、非法 gain、跨空间和非 audio 资源返回 422，整批不落库；configuration 更新沿用 `Idempotency-Key`，同键同载荷回放，异载荷返回 `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`。
- `/capabilities` 的 `slideshow.audio` 当前为 `audio_assets=true`、`page_narration=false`、`audio_cues=false`；不会提前宣称 cue 可用。
- 已运行：`uv run --project backend pytest -c backend/pyproject.toml backend/tests/api/test_external_audio.py ...`（本批 48 passed）；`pnpm run codegen:editor-api`、`pnpm run test:contracts:generated` 通过；External API 参考文档已补音频章节。
- 未完成：`web-presentation-cli` 的 `--type audio` 与项目音频读写、`web-presentation-mcp` 的异步客户端/工具 Schema 均未在本仓实现，M2 出口仍需独立仓交付与发布验证。

建议提交标题：主仓 `WP19：交付音频 External API`；独立仓使用各自中文提交并在本卡回填版本。
