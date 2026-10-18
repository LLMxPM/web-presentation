# WP14：cue 快照、构建、模板与引用

状态：待实施。阶段：M2。主责：Backend / Runtime 构建。

## 前置与输入

前置完成：[WP05](./wp05-artifact-packages-references.md)、[WP13](./wp13-audio-settings-storage.md)。

## 修改范围与交付

- preview/build 快照把 cue 资产 ID 解析为逻辑名、gain 和固定 hash，不下发数据库 ID 或持久票据。
- `ProjectArtifactBuilder` 主动收集 cue 绑定资源，即使页面源码未引用也进入 assets manifest。
- 资源引用摘要列出项目和 cue key；归档/删除按现有引用策略保护。
- 项目模板包导出音量、逻辑绑定和音频文件；导入按目标工作空间重建资产 ID，保持事务原子性。
- 更新 artifact/template Schema、版本兼容、共享样例和指纹输入。

## 完成标准

- [ ] artifact 创建后修改项目/资源不改变旧快照。
- [ ] cue 资产不依赖页面引用也能进入预览和独立构建。
- [ ] 模板包跨工作空间往返等价，名称冲突和缺文件有明确错误。
- [ ] 资源引用保护、构建持有和清理不遗漏 cue-only 资产。

建议提交标题：`WP14：贯通 cue 快照与包引用`。
