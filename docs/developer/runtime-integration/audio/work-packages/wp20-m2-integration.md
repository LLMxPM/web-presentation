# WP20：M2 音效联调与发布门槛

状态：待验收（代码与自动化已准备；真实 Chromium/长稳、浏览器矩阵与 CLI/MCP 交付未完成）。阶段：M2 出口。主责：跨模块验证 / 发布。

## 前置与输入

前置完成：[WP16](./wp16-transition-cues.md)、[WP17](./wp17-interaction-composable.md)、[WP18](./wp18-editor-audio-settings.md)、[WP19](./wp19-external-clients.md)。

## 修改范围与交付

- 对照验收 A14–A20 完成 cue 存储、切页、点击、并发、执行上下文、配置往返和长稳。
- 真实 Chromium 必测；Firefox/WebKit 记录格式和策略矩阵；独立构建产物验证无 Backend/外网依赖。
- 开放项目 audio/cue capability、Editor 入口和 Runtime Kit `useAudioCue.v1`。
- 更新用户文档、Runtime Kit 能力、External API、CLI/MCP 和兼容矩阵；仍明确 BGM/混音/音频导出不支持。

## 完成标准

- [ ] A14–A20 全部有自动化和实机证据。
- [ ] 1000 次 transition、1000 次 interaction、200 次导航后无对象/监听/声音泄漏。
- [ ] Backend、Editor、Runtime、Renderer、契约、CLI、MCP 和适用 E2E 门禁通过，或清楚记录被限制的发布面。
- [ ] 本卡回填版本组合、命令、结果、浏览器矩阵、产物 hash 和未运行项。

## 当前证据（2026-10-18）

- 自动化已覆盖：ABAC/引用/模板包（Backend 48 项本批目标测试）、切页精确 generation 与 200 次连续导航、1000 次 transition + 1000 次 interaction 的固定实例池、静音/冻结/卸载监听清理、Editor 音频设置保存与 capability 隐藏。
- 已运行：Runtime `pnpm run test`（152 files / 1213 passed / 3 skipped）、`vue-tsc -b`；Editor `check`、`test`（158 files / 895 passed）、`build`；Backend 音频/External 目标测试 48 passed；`pnpm run test:contracts:generated` 与根契约测试 110 passed。
- 当前 capability 仍只开放 `audio_assets`；`page_narration` 与 `audio_cues` 保持 false，Editor 音频标签页和 `useAudioCue.v1` 未向最终用户宣称可用。
- 未运行：真实 Chromium/Firefox/WebKit 的 autoplay、试听、切页/点击长稳与执行上下文验收；独立构建产物无 Backend/外网依赖验证；Renderer 相关门禁；CLI/MCP 独立仓交付与真实流程；数据库迁移在真实 SQLite/PostgreSQL 的 upgrade/downgrade 演练。
- 结论：M2 不能宣布发布完成；在完成上述实机证据前不得修改 `AUDIO_OPEN_CAPABILITIES` 开放 cue，也不得更新用户文档宣称音效可用。

## Review 修复（2026-10-19）

独立 review 在开放 capability 前发现 3 个 P1 播放链路问题与 2 个 P2 边界问题，均已修复并补回归测试：

- 旁白有效音量：`AudioViewer` 现在按 `master × narration × AssetAudio.volume` 设置原生音量；内容音频保持组件音量，任一项目音量为 0 时旁白静音。
- 兜底错误语义：主音频失败切换到 `fallbackSrc` 时只发 `media-reset`，兜底也失败才发 `error`；放映宿主不会在兜底仍可发声时中止。
- BFCache 恢复：`pageshow.persisted=true` 先停残留短音效，再按可见性恢复，修复恢复后 cue 永久 suspend。
- 公开 key 边界：`useAudioCue.v1` 与注入服务只接受合法 `interaction.*`；`transition.*` 只能由切页单通道触发。
- Editor 资源选择器：分页“加载更多”最多按 100 条追加；未加载的已绑定资源保留占位并在加载后替换。
- 复验已运行：Runtime `pnpm run test`（152 files / 1219 passed / 3 skipped）、`vue-tsc -b`；Editor `check`、`test`（158 files / 896 passed）、`build`。capability 仍保持关闭，实机证据缺口不变。

建议提交标题：`WP20：完成 M2 页面音效联调`。
