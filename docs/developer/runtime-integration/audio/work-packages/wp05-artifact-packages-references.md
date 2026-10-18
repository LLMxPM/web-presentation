# WP05：引用、artifact、构建与包往返

状态：待验收（引用、构建、包与静态导出链路已完成自动化验证，独立离线播放并入 WP06）。阶段：M0。主责：Backend / Runtime 构建。

## 前置与输入

前置完成：[WP02](./wp02-backend-audio-assets.md)、[WP04](./wp04-runtime-kit-asset-audio.md)。

## 修改范围与交付

- 验证通用 `Asset* name` 解析能收集 `AssetAudio`，为 props 和多旁白增加专用静态校验。
- 页面、组件、previewSchema、建议资源、构建额外资源和引用摘要完整识别 audio。
- preview artifact 与 build release 固化音频 name→hash；Build Worker 物化文件后不依赖 Backend 或外部 CDN。
- 组件包、样式/项目模板包中包含实际引用的音频文件，导入后重建资源绑定并保持字节 hash。
- 静态导出识别 audio media kind，明确省略且不泄露票据。

## 完成标准

- [x] 页面/组件引用使归档或删除保护生效，动态 name 的限制有明确诊断。
- [x] 构建创建后替换音频不改变旧 release；attempt 围栏和资源持有不退化。
- [x] 模板包导出→导入→再导出语义等价，失败无半包残留。
- [ ] 关闭 Backend/外网后，独立构建仍可手动播放音频。

建议提交标题：`WP05：贯通音频引用与构建包链路`。

## 实施记录

- 引用校验：新增 `audio_options_gate`，复用 `AssetAudioPropsContract` 静态校验 purpose、controls、volume、playbackRate、preload、loop 与同一源码多旁白；接入页面版本保存、组件发布和 `CodeCheckService` 候选源码预检。动态绑定跳过静态判定，交由 Runtime 兜底。
- 引用与构建：通用 `Asset* name` 解析已收集 `AssetAudio`；构建快照、构建资源摘要、组件包、资源包与项目模板包复用同一资源集合，不新增第二套类型清单。
- 静态导出：PPTX 媒体词汇表新增 `audio`，原生 audio 与 `.audio-viewer` 均按 skipped 记录“首版 PPTX 导出省略音频”；浏览器打印/PDF 通过打印 CSS 隐藏音频根节点。PDF/PPTX 不等待播放、不写临时票据。
- 已运行：
  - `uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_audio_options_gate.py backend/tests/unit/test_resource_reference_parser.py backend/tests/api/test_workspace_audio_assets.py backend/tests/api/test_project_template_package_import.py backend/tests/integration/test_project_build.py -q`：69 项通过。
  - `uv run --project backend pytest -c backend/pyproject.toml backend/tests/api/test_component_share_audio_package.py -q`：1 项通过。
  - `pnpm exec vitest run src/core/services/pptx/PPTXRuntimeKitExportDom.test.ts src/core/services/pptx/PPTXDomConverter.part2.test.ts src/core/services/BrowserPrintService.test.ts`：3 个文件、79 项通过。
  - `pnpm --filter web-runtime-vue check` 与新增/触碰文件 ESLint：通过。
- 未运行：Build Worker 在完全断网环境物化音频并手动播放，留到 WP06 独立构建产物验证。
