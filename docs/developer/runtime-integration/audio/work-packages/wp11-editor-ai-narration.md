# WP11：Editor 与 AI 旁白创作约束

状态：待验收（Editor 提示、AI 规格与防漂移测试完成，能力开放并入 WP12）。阶段：M1。主责：Editor / Backend AI。

## 前置与输入

前置完成：[WP08](./wp08-narration-lifecycle.md)、[WP09](./wp09-media-end-errors.md)。实施 UI 前读取 `DESIGN.md`。

## 修改范围与交付

- Editor 在资源/页面使用说明中提供 `AssetAudio.v1 purpose="narration"` 的明确示例和限制。
- 能取得音频 duration 时，对 timer 小于旁白时长给出非阻断警告，并建议 `media_end`；不自动改配置。
- Backend 代码检查识别 narration+loop、多旁白、非法数值和动态 name 限制，返回有界诊断。
- 先更新 `tool_specs.py`，再让内容助手查询 audio、复用现有资产并生成版本化 import。
- 不增加 AI 配音生成、字幕、路由级旁白覆盖或任意远程 URL。

## 完成标准

- [x] AI 工具目录、披露、说明和示例由单一规格派生且防漂移测试通过。
- [x] Editor 警告不会阻止合法 timer 保存，也不会误改 advance mode。
- [x] 自动生成页面只使用资源逻辑名和 `AssetAudio.v1`，不使用 autoplay。
- [x] Runtime capability 未开放时 UI/AI 不宣称旁白可用。

建议提交标题：`WP11：补齐旁白创作与 AI 约束`。

## 实施记录

- 代码版本：本工作包所在提交。
- AI 规格：`tool_specs.py` 的 asset 查询、runtime_kit 详情和 list_entities 说明补充 audio 资源、稳定 name、版本化 `AssetAudio.v1` 与旁白能力门槛；`agent_catalog.py` 的平台背景、Runtime Kit 组件和视觉选型说明同步加入音频。代码规范明确“只有 Runtime Kit 能力摘要声明旁白自动播放已开放才使用 narration”，能力未开放时只使用 content，不暴露 autoplay、旁白禁 loop、同一页面最多一个旁白目标。防漂移断言覆盖目录提示词、代码规范、asset/runtime_kit 手册。
- Editor：资源详情说明 audio 的 content/narration 用法、能力条件与无远程 URL/autoplay；项目放映设置和页面级覆盖的 timer 旁白给出非阻断提示，不修改草稿或 advance mode。
- 已知缺口：Editor 放映配置面当前无法直接取得页面旁白资源的 duration，因此未实现“timer 小于旁白时长”的具体数值比较，也没有为此新增接口；保留通用 timer 旁白警示，待 WP12 真机联调后按实际数据可得性决定是否补专用读取链路。
- 已运行：
  - `uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_ai_agent_catalog.py backend/tests/unit/test_unified_tool_specs.py backend/tests/unit/test_audio_options_gate.py -q`：15 项通过。
  - `pnpm --filter editor exec vitest run src/components/project/ProjectSlideshowFields.test.ts src/components/project/ProjectPresentationConfigDialog.test.ts src/components/project/ProjectRouteSlideshowForm.test.ts`：12 项通过。
  - `pnpm --filter editor check`、`pnpm --filter web-runtime-vue check`、触碰文件 ESLint：通过。
- 未运行：真实内容助手会话生成旁白页面、真实 duration 比较和 capability 开放后的 UI 联调，留到 WP12。
