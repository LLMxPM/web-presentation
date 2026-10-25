# WP01：冻结音频契约与共享样例

状态：完成（2026-10-18）。阶段：M0。主责：Backend / 跨模块契约。

## 前置与输入

无。以[统一契约](../../../runtime-integration/audio/contract.md)为输入。

## 修改范围与交付

- 冻结 `audio` 资源词汇、允许扩展名/MIME、`AssetAudio.v1` props、media purpose、项目音量、cue key 和 artifact camelCase 结构。
- 增加跨 Backend/Editor/Runtime 可消费的正反例，覆盖严格数字、非法 key、narration+loop、多旁白和历史默认值。
- 定义 capability 名称和阶段开放顺序，避免 M0 提前宣称旁白/cue 可用。
- 交付契约测试骨架和 fixtures；本包不修改数据库、不开放 API、不播放任何声音。

## 完成标准

- [x] 契约评审确认资源、页面媒体、cue 和静态上下文边界。
- [x] snake_case/camelCase 样例可确定性转换，非法输入有明确错误语义。
- [x] 共享 fixture 纳入根仓契约测试且不复制第二份默认值。
- [x] 记录测试命令、结果和未运行项。

建议提交标题：`WP01：冻结音频契约与共享样例`。

## 实施记录

- 契约代码：`backend/app/schemas/audio.py`，统一维护格式/MIME、三阶段 capability、`AssetAudio.v1` 属性、严格三段音量、cue key/绑定、历史默认值和 Runtime camelCase 映射。
- 共享样例：`tests/fixtures/audio-contract-cases.json`，包含资源格式、阶段能力、项目设置、cue、AssetAudio 和 Runtime 映射正反例。
- Backend 验证：`.venv/Scripts/python.exe -m pytest backend/tests/unit/test_audio_schema.py -q` → 34 passed；`.venv/Scripts/python.exe -m ruff check backend/app/schemas/audio.py backend/tests/unit/test_audio_schema.py` → 通过。
- 根仓验证：`pnpm exec vitest run --config tests/config/vitest.config.ts tests/contracts/audio-contract.test.ts` → 1 file / 6 passed；`pnpm run test:contracts` → 18 files / 110 passed。
- 未运行：数据库、HTTP、Editor、Runtime 播放和真实浏览器测试；本包按提交边界不修改这些能力，由 WP02 以后覆盖。
