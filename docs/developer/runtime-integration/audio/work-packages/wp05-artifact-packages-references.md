# WP05：引用、artifact、构建与包往返

状态：待实施。阶段：M0。主责：Backend / Runtime 构建。

## 前置与输入

前置完成：[WP02](./wp02-backend-audio-assets.md)、[WP04](./wp04-runtime-kit-asset-audio.md)。

## 修改范围与交付

- 验证通用 `Asset* name` 解析能收集 `AssetAudio`，为 props 和多旁白增加专用静态校验。
- 页面、组件、previewSchema、建议资源、构建额外资源和引用摘要完整识别 audio。
- preview artifact 与 build release 固化音频 name→hash；Build Worker 物化文件后不依赖 Backend 或外部 CDN。
- 组件包、样式/项目模板包中包含实际引用的音频文件，导入后重建资源绑定并保持字节 hash。
- 静态导出识别 audio media kind，明确省略且不泄露票据。

## 完成标准

- [ ] 页面/组件引用使归档或删除保护生效，动态 name 的限制有明确诊断。
- [ ] 构建创建后替换音频不改变旧 release；attempt 围栏和资源持有不退化。
- [ ] 模板包导出→导入→再导出语义等价，失败无半包残留。
- [ ] 关闭 Backend/外网后，独立构建仍可手动播放音频。

建议提交标题：`WP05：贯通音频引用与构建包链路`。
