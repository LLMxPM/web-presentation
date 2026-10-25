# WP04：Runtime Kit `AssetAudio.v1`

状态：待验收（组件、manifest 与自动化验证已完成，真实浏览器播放并入 WP06）。阶段：M0。主责：Runtime Kit。

## 前置与输入

前置完成：[WP01](wp01-contract-fixtures.md)、[WP02](wp02-backend-audio-assets.md)。

## 修改范围与交付

- 新增 `AssetAudio.v1.vue` 和内部 AudioViewer，使用 `useAssetSrc.v1` 解析资源，公开属性与契约一致。
- 输出 `data-runtime-media-target`、`data-runtime-media-purpose`、`data-runtime-kit-media-kind=audio` 等稳定标记。
- `AssetRenderer` 与 asset-preview 支持 `render_type=audio`；资源预览显示 controls 且不自动播放。
- 更新 Runtime Kit manifest 的参数 Schema、约束、示例和版本化 import path，补防漂移测试。
- M0 只验证 content 手动播放；narration 自动播放仍由 capability 禁用。

## 完成标准

- [x] name 命中、fallback、音量、速率、preload、loop 与 controls 有组件测试。
- [x] narration+loop 和数值越界被静态或运行时校验，错误有界。
- [x] 静态上下文强制不自动播放并使用 `preload=none`。
- [x] Runtime Kit manifest、Backend 允许清单和导入检查一致。

建议提交标题：`WP04：新增 AssetAudio.v1`。

## 实施记录

- 代码版本：本工作包提交。
- 已实现：公开 `AssetAudio.v1` 与内部 `AudioViewer`，严格校验 purpose/controls/volume/playbackRate/preload/loop，静态上下文强制 `preload=none` 且不暴露 autoplay；主资源加载失败时只尝试一次 fallback URL，再失败进入有界文案占位。`AssetRenderer`、资源预览与共享 `RuntimePreviewAssetMetadata` 已识别 `render_type=audio`。
- manifest：新增 `AssetAudio.v1` 参数 Schema、约束、示例和两个预览 preset；Backend 直接消费同一 manifest，无第二份允许清单。
- 已运行：
  - `pnpm exec vitest run src/runtime-kit/internal/renderers/AudioViewer.test.ts src/runtime-kit/internal/renderers/audio-options.test.ts src/runtime-kit/public/components/assets/AssetAudio.v1.test.ts src/runtime-kit/manifest/runtime-kit.manifest.test.ts`：4 个文件、34 项通过。
  - `pnpm --filter web-runtime-vue check`：通过。
  - 对新增/触碰文件运行 ESLint：通过。
  - `uv run --project backend pytest -c backend/pyproject.toml backend/tests/contracts/test_runtime_module_policy.py -q`：9 项通过。
- 未运行：真实 Chromium/Firefox/WebKit 播放、fallback 与格式兼容矩阵，留到 WP06 的独立 E2E 环境统一验收。
