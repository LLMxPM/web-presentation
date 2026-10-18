# WP11：Editor 与 AI 旁白创作约束

状态：待实施。阶段：M1。主责：Editor / Backend AI。

## 前置与输入

前置完成：[WP08](./wp08-narration-lifecycle.md)、[WP09](./wp09-media-end-errors.md)。实施 UI 前读取 `DESIGN.md`。

## 修改范围与交付

- Editor 在资源/页面使用说明中提供 `AssetAudio.v1 purpose="narration"` 的明确示例和限制。
- 能取得音频 duration 时，对 timer 小于旁白时长给出非阻断警告，并建议 `media_end`；不自动改配置。
- Backend 代码检查识别 narration+loop、多旁白、非法数值和动态 name 限制，返回有界诊断。
- 先更新 `tool_specs.py`，再让内容助手查询 audio、复用现有资产并生成版本化 import。
- 不增加 AI 配音生成、字幕、路由级旁白覆盖或任意远程 URL。

## 完成标准

- [ ] AI 工具目录、披露、说明和示例由单一规格派生且防漂移测试通过。
- [ ] Editor 警告不会阻止合法 timer 保存，也不会误改 advance mode。
- [ ] 自动生成页面只使用资源逻辑名和 `AssetAudio.v1`，不使用 autoplay。
- [ ] Runtime capability 未开放时 UI/AI 不宣称旁白可用。

建议提交标题：`WP11：补齐旁白创作与 AI 约束`。
