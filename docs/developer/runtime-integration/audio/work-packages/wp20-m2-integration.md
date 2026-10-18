# WP20：M2 音效联调与发布门槛

状态：待实施。阶段：M2 出口。主责：跨模块验证 / 发布。

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

建议提交标题：`WP20：完成 M2 页面音效联调`。
