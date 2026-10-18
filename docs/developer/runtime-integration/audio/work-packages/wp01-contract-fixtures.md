# WP01：冻结音频契约与共享样例

状态：待实施。阶段：M0。主责：Backend / 跨模块契约。

## 前置与输入

无。以[统一契约](../contract.md)为输入。

## 修改范围与交付

- 冻结 `audio` 资源词汇、允许扩展名/MIME、`AssetAudio.v1` props、media purpose、项目音量、cue key 和 artifact camelCase 结构。
- 增加跨 Backend/Editor/Runtime 可消费的正反例，覆盖严格数字、非法 key、narration+loop、多旁白和历史默认值。
- 定义 capability 名称和阶段开放顺序，避免 M0 提前宣称旁白/cue 可用。
- 交付契约测试骨架和 fixtures；本包不修改数据库、不开放 API、不播放任何声音。

## 完成标准

- [ ] 契约评审确认资源、页面媒体、cue 和静态上下文边界。
- [ ] snake_case/camelCase 样例可确定性转换，非法输入有明确错误语义。
- [ ] 共享 fixture 纳入根仓契约测试且不复制第二份默认值。
- [ ] 记录测试命令、结果和未运行项。

建议提交标题：`WP01：冻结音频契约与共享样例`。
