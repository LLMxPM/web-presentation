# WP12：M1 页面旁白联调门槛

状态：待实施。阶段：M1 出口。主责：跨模块验证 / 发布。

## 前置与输入

前置完成：[WP10](./wp10-mute-presenter-static.md)、[WP11](./wp11-editor-ai-narration.md)。

## 修改范围与交付

- 对照验收 A07–A13 完成开始时序、生命周期、推进模式、错误恢复、静音、双窗口和长稳。
- 使用真实受保护音频与独立构建产物验证，不只运行 jsdom mock。
- 开放 narration capability，并同步 Runtime Kit/Backend/Editor 兼容矩阵。
- 更新用户旁白文档；仍明确不支持 cue、跨页 BGM、AI 配音和音频导出。

## 完成标准

- [ ] A07–A13 全部通过并保留时间戳/generation/播放窗口证据。
- [ ] Backend、Editor、Runtime、Renderer、契约和适用 E2E 门禁通过。
- [ ] 至少 100 次翻页和 30 分钟旁白循环无资源线性增长。
- [ ] 卡片回填版本、命令、结果、未运行项与已知浏览器限制。

建议提交标题：`WP12：完成 M1 页面旁白联调`。
