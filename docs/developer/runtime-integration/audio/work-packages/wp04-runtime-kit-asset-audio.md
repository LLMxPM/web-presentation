# WP04：Runtime Kit `AssetAudio.v1`

状态：待实施。阶段：M0。主责：Runtime Kit。

## 前置与输入

前置完成：[WP01](./wp01-contract-fixtures.md)、[WP02](./wp02-backend-audio-assets.md)。

## 修改范围与交付

- 新增 `AssetAudio.v1.vue` 和内部 AudioViewer，使用 `useAssetSrc.v1` 解析资源，公开属性与契约一致。
- 输出 `data-runtime-media-target`、`data-runtime-media-purpose`、`data-runtime-kit-media-kind=audio` 等稳定标记。
- `AssetRenderer` 与 asset-preview 支持 `render_type=audio`；资源预览显示 controls 且不自动播放。
- 更新 Runtime Kit manifest 的参数 Schema、约束、示例和版本化 import path，补防漂移测试。
- M0 只验证 content 手动播放；narration 自动播放仍由 capability 禁用。

## 完成标准

- [ ] name 命中、fallback、音量、速率、preload、loop 与 controls 有组件测试。
- [ ] narration+loop 和数值越界被静态或运行时校验，错误有界。
- [ ] 静态上下文强制不自动播放并使用 `preload=none`。
- [ ] Runtime Kit manifest、Backend 允许清单和导入检查一致。

建议提交标题：`WP04：新增 AssetAudio.v1`。
