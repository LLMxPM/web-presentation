# WP02：Backend 音频资源类型与读取链路

状态：完成（2026-10-18）。阶段：M0。主责：Backend。

## 前置与输入

前置完成：[WP01](wp01-contract-fixtures.md)。

## 修改范围与交付

- 在 `AssetType`、Schema、资源角色、上传/替换校验和 External 资源接口加入 `audio`。
- 允许契约规定的扩展名/MIME，拒绝伪造组合、空文件和不受支持格式；保持音频不可文本编辑且不参与比例回填。
- 复核私有文件的 Content-Type、HEAD、Range、缓存和权限顺序，补音频 seek/分段读取测试。
- 更新 OpenAPI 与 Editor 生成类型，不在手写类型中遗留第二份枚举。
- 不实现转码、时长分析、波形或 cue 存储。

## 完成标准

- [x] 音频上传、替换、历史、下载、归档/恢复沿用统一服务并通过 API 测试。
- [x] 跨工作空间、过期票据、错误 hash、Range 越界和 MIME 伪造均按现有错误体系拒绝。
- [x] SQLite/PostgreSQL 无需枚举列迁移的判断有测试或模型证据。
- [x] OpenAPI 生成物与 Backend Schema 无漂移。

建议提交标题：`WP02：增加 Backend audio 资源类型`。

## 实施记录

- Backend：`AssetType.AUDIO`、音频 content role、项目建议资源类型和统一上传/替换链路已接入；允许格式直接复用 WP01 单一常量，扩展名必须与对应 MIME 精确匹配，缺失 MIME 和 `application/octet-stream` 均拒绝。
- 文件交付：复用既有鉴权优先、ETag、HEAD 与单段 Range 逻辑；音频专项验证 `Content-Type`、`Accept-Ranges`、`Content-Range` 和 304。`WorkspaceAsset.asset_type` 保持 SQLAlchemy `String`，无需数据库枚举迁移。
- 契约：运行 `pnpm run codegen:editor-api`，OpenAPI 为 260 paths / 351 schemas；Editor `AssetType` 改为生成类型别名，必要的穷举映射补 audio，但资源页入口留给 WP03。
- 验证：音频 API 专项 `.venv/Scripts/python.exe -m pytest backend/tests/api/test_workspace_audio_assets.py -q` → 17 passed；资源/建议资源/交付回归四文件首轮合跑 → 52 passed（补充音频复制/归档/恢复用例后专项复跑全绿）；`pnpm run test:contracts:generated` → 完全一致；`pnpm run test:editor:check` → 通过；新增测试和小型触碰文件 Ruff → 通过。
- 未运行：音频资源 Editor 试听、Runtime 预览、artifact/build/package 和真实浏览器 seek；分别由 WP03–WP06 验收。
