# WP18：Editor 项目音频设置

状态（2026-10-25）：已实现并随 cue 能力默认开放；真实浏览器的小屏、键盘与试听走查仍待补证。阶段：M2。主责：Editor。

## 前置与输入

前置完成：[WP13](wp13-audio-settings-storage.md)、[WP14](wp14-cue-snapshot-packages.md)。实施前读取根目录 `DESIGN.md`。

## 修改范围与交付

- 在项目展示配置中增加独立“音频”分区，编辑 master/narration/effects 音量。
- 配置前进/后退系统 cue 和 `interaction.*` 绑定；资源选择器仅列 active audio。
- 支持显式试听、替换、清空、未保存提示、加载/错误/空态和继承说明。
- 展示最终增益的可理解摘要；试听尊重当前 master/effects 设置并在 dialog 关闭时停止。
- capability 未开放时隐藏或只读，不提交旧 Runtime 无法执行的配置。

## 完成标准

- [x] 保存、重新打开、清空、并发错误和旧客户端数据映射有组件测试。
- [x] 选择非 audio 或跨 workspace 即使伪造请求也由 Backend 拒绝。
- [ ] 小屏、滚动、键盘操作和试听停止符合设计规范（JSDOM 已覆盖行为，真实浏览器走查待 WP20）。
- [x] Editor 生成类型、类型检查、单测和构建通过。

## 实施记录（2026-10-18）

- 项目设置新增第三个“音频”标签页，包含主/旁白/音效三段音量、前进/后退固定 cue、`interaction.*` 增删、绑定增益和最终音量摘要（主 × 音效 × 绑定）。
- 资源选择器只请求 `asset_type=audio&status=active`；加载、失败重试、空资源与缺少工作空间都有明确状态。试听由显式按钮触发，使用当前音量计算值，dialog 关闭、标签切换和组件卸载时停止。
- 保存前统一校验音量为 0–100 整数、交互 key 形如 `interaction.confirm`、key 唯一、已填 key 必须选择资源；交互行“删除”直接移除草稿项。旧项目缺少 `audio_settings` 时映射默认音量且不绑定 cue。
- 服务端能力新增 `slideshow.audio`；在 2026-10-18 当时仅开放 `audio_assets`，`audio_cues=false` 时 Editor 隐藏音频标签且保存不提交 `audio_settings`。2026-10-25 已默认开放 cue，音频标签随能力声明显示。
- 已运行：`pnpm --filter editor check`、`pnpm --filter editor test`（158 files / 895 tests passed）、`pnpm --filter editor build` 通过；定向音频测试 17 项通过。
- 未运行：真实浏览器下的 Tab/小屏布局走查与 cue 试听混音，等待 WP20。

## Review 修复（2026-10-19）

- 资源选择器改为分页：首次加载 100 条，可“加载更多”追加并按 ID 去重；超过一页时显示已加载/总数。加载更多失败保留已加载内容并可重试。
- 已绑定但尚未加载到当前页的资源保留禁用占位（`资源 #ID（加载更多后可选）`），加载完成后自动替换为真实名称；下拉按解析状态重建，避免 Reka 复用旧占位标签。
- 已运行：`pnpm --filter editor check`、`pnpm --filter editor test`（158 files / 896 tests passed）、`pnpm --filter editor build` 通过。

建议提交标题：`WP18：增加项目音频与 cue 配置`。
