# WP02：Backend 音频资源类型与读取链路

状态：待实施。阶段：M0。主责：Backend。

## 前置与输入

前置完成：[WP01](./wp01-contract-fixtures.md)。

## 修改范围与交付

- 在 `AssetType`、Schema、资源角色、上传/替换校验和 External 资源接口加入 `audio`。
- 允许契约规定的扩展名/MIME，拒绝伪造组合、空文件和不受支持格式；保持音频不可文本编辑且不参与比例回填。
- 复核私有文件的 Content-Type、HEAD、Range、缓存和权限顺序，补音频 seek/分段读取测试。
- 更新 OpenAPI 与 Editor 生成类型，不在手写类型中遗留第二份枚举。
- 不实现转码、时长分析、波形或 cue 存储。

## 完成标准

- [ ] 音频上传、替换、历史、下载、归档/恢复沿用统一服务并通过 API 测试。
- [ ] 跨工作空间、过期票据、错误 hash、Range 越界和 MIME 伪造均按现有错误体系拒绝。
- [ ] SQLite/PostgreSQL 无需枚举列迁移的判断有测试或模型证据。
- [ ] OpenAPI 生成物与 Backend Schema 无漂移。

建议提交标题：`WP02：增加 Backend audio 资源类型`。
