# WP03：Editor 音频资源管理与试听

状态：待验收（实现与自动化验证已完成，真实浏览器试听并入 WP06）。阶段：M0。主责：Editor。

## 前置与输入

前置完成：[WP01](wp01-contract-fixtures.md)、[WP02](wp02-backend-audio-assets.md)。实施前读取根目录 `DESIGN.md`。

## 修改范围与交付

- 在资源筛选、上传 accept、项目资源面板、详情、包资源选择和类型标签中加入“音频”。
- 提供显式播放的试听控件、加载/空态/错误态和格式提示；打开详情或切换资源不得自动播放。
- 支持替换、历史、复制、归档、恢复、引用摘要和原始下载。
- 音频不显示文本编辑、图片背景、宽高比回填或模型分析入口。
- 增加组件测试与真实浏览器试听检查；不实现项目 cue 表单和波形编辑。

## 完成标准

- [x] MP3 等允许格式可选择并上传，错误扩展名在前端提示且 Backend 仍最终校验。
- [x] 同时切换多个预览时旧音频停止，dialog 关闭后无残余声音。
- [ ] active/archived/history 和小屏布局均可用。
- [x] Editor 类型检查、单测和构建通过。

## 实施记录

- 代码版本：本工作包提交。
- 已实现：完整资源库与项目资源面板的音频类型入口、上传 accept、原生显式试听、元数据/错误提示、详情替换与二进制编辑边界。
- 已运行：
  - `corepack pnpm --dir editor exec vitest run src/components/project/AssetAudioPreview.test.ts src/components/project/AssetManagerPanel.test.ts --reporter=verbose`：10 项中修正 1 项测试选择器后全部通过。
  - `corepack pnpm --dir editor exec vitest run src/components/project/AssetManagerPanel.test.ts src/views/AssetsView.test.ts --reporter=verbose`：27 项通过。
  - `corepack pnpm --dir editor exec vitest run src/components/project/asset-manager.test.ts --reporter=verbose`：7 项通过。
  - `corepack pnpm --filter editor check`：通过。
  - `corepack pnpm --filter editor build`：通过。
- 未运行：真实浏览器试听与小屏检查。2026-10-18 探测时 Editor/Runtime 正常，Backend 及其 PostgreSQL、Redis 不可达；不重复启动服务或修改开发配置，留到 WP06 的独立 E2E 环境统一验收。

建议提交标题：`WP03：增加 Editor 音频资源管理与试听`。
