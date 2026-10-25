# WP06：M0 音频资源联调门槛

状态（2026-10-25）：主要 Chromium 实机证据已补齐，原 A01–A06 全格式和浏览器矩阵未全部关闭；`audio_assets` 已按实际范围开放。阶段：M0 出口。主责：跨模块验证 / 发布。

后续证据见[动画前联合验收](../../../../archive/developer-work-2026-10/pre-motion-joint-acceptance.md)：真实 CLI WAV 上传/下载/替换、受保护音频 Range/HEAD/304 与鉴权负例、MP3 手动播放和离页停播、PDF/PPTX 静态禁播、含 WAV 的独立 ZIP 与模板包往返均通过。M4A/OGG、Firefox/WebKit，以及 A01–A06 未逐项覆盖的操作和格式仍按实际支持范围记录，不把这轮样本写成全矩阵通过。

## 前置与输入

前置完成：[WP03](wp03-editor-audio-assets.md)、[WP04](wp04-runtime-kit-asset-audio.md)、[WP05](wp05-artifact-packages-references.md)。

## 修改范围与交付

- 对照验收 A01–A06 完成资源、权限、试听、引用、构建、包和静态导出联调。
- 在 Chromium 必测，并记录 Firefox/WebKit 对允许格式的实际结果；不能以 MIME 表推测兼容。
- 核对 capability：只开放 audio 资源和手动 content 播放，旁白与 cue 保持关闭。
- 更新开发文档和兼容矩阵；只有阶段通过后才补用户资源文档。

## 完成标准

- [ ] A01–A06 全部有自动化与实机证据。
- [ ] Backend、Editor、Runtime、Renderer 和契约最小充分门禁通过。
- [ ] 没有提交无授权测试音频、大型录屏或可重新生成构建产物。
- [ ] 本卡回填版本、命令、结果、浏览器/格式矩阵和未运行项。

建议提交标题：`WP06：完成 M0 音频资源联调`。
