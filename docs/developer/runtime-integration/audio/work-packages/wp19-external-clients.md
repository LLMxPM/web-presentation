# WP19：External API、CLI 与 MCP

状态：待实施。阶段：M2。主责：Backend / `web-presentation-cli` / `web-presentation-mcp`。

## 前置与输入

前置完成：[WP13](./wp13-audio-settings-storage.md)、[WP14](./wp14-cue-snapshot-packages.md)。

## 修改范围与交付

- 主仓 External API 暴露 audio 上传/查询/替换和项目音量/cue 读取更新，补 scope、幂等、错误及 capability。
- 运行 Editor API codegen 和契约防漂移，更新 External API 参考文档。
- CLI 增加 `--type audio`、项目音频配置读写、清空和可读输出；不返回持久私有 URL。
- MCP 增加异步客户端与严格工具 Schema，资产和绑定返回 ID、逻辑名、类型及摘要。
- 三个仓分别记录测试和版本；允许分步交付，但 M2 出口必须明确未完成消费者的发布限制。

## 完成标准

- [ ] 同幂等键同载荷回放不重复写，异载荷冲突。
- [ ] 省略、空列表、非法 key、跨 workspace 和非 audio 错误语义三端一致。
- [ ] CLI/MCP 能完成上传→绑定→查询→替换→清空真实流程。
- [ ] 独立仓文档、Skill/工具说明和构建分发测试同步。

建议提交标题：主仓 `WP19：交付音频 External API`；独立仓使用各自中文提交并在本卡回填版本。
