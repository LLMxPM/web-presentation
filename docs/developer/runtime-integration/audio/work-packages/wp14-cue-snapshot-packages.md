# WP14：cue 快照、构建、模板与引用

状态：已实现，待 WP20 联调。阶段：M2。主责：Backend / Runtime 构建。

## 前置与输入

前置完成：[WP05](./wp05-artifact-packages-references.md)、[WP13](./wp13-audio-settings-storage.md)。

## 修改范围与交付

- preview/build 快照把 cue 资产 ID 解析为逻辑名、gain 和固定 hash，不下发数据库 ID 或持久票据。
- `ProjectArtifactBuilder` 主动收集 cue 绑定资源，即使页面源码未引用也进入 assets manifest。
- 资源引用摘要列出项目和 cue key；归档/删除按现有引用策略保护。
- 项目模板包导出音量、逻辑绑定和音频文件；导入按目标工作空间重建资产 ID，保持事务原子性。
- 更新 artifact/template Schema、版本兼容、共享样例和指纹输入。

## 完成标准

- [x] artifact 创建后修改项目/资源不改变旧快照。
- [x] cue 资产不依赖页面引用也能进入预览和独立构建。
- [x] 模板包跨工作空间往返等价，名称冲突和缺文件有明确错误。
- [x] 资源引用保护、构建持有和清理不遗漏 cue-only 资产。

## 实施记录（2026-10-18）

- artifact config bundle 顶层新增 `audio`，由 `ProjectAudioSettingsService.build_runtime_config` 生成；只输出 active、同工作空间 audio 资源的逻辑名和 gain，缺资源绑定静默跳过。
- 预览、构建与模板预览统一经 `collect_config_asset_names` 收集 `audio.cues.*.assetName`，cue-only 资源会进入 manifest 和构建产物。
- 模板包 Schema 升级到 4，导出音量与逻辑 cue，导入先解析/创建音频资产再原子重建绑定；Schema 1–3 仍可导入并按默认音量处理，Schema 4 缺少音频设置或引用包内不存在的音频时返回明确错误。
- `AssetReferenceSummary` 增加 `project_audio_cue_count`，资源归档/删除保护纳入项目 cue 引用。
- 已运行：`uv run --project backend pytest -c backend/pyproject.toml backend/tests/api/test_project_preview_slideshow.py backend/tests/api/test_project_template_package_import.py backend/tests/api/test_project_template_package_slideshow.py backend/tests/api/test_workspace_audio_assets.py backend/tests/integration/test_project_build.py -q`，与 WP13 合计 62 passed。
- 未运行：真实 Runtime 构建 Worker/下载 ZIP 的端到端往返；执行上下文与 cue 真机播放留待 WP20。

建议提交标题：`WP14：贯通 cue 快照与包引用`。
