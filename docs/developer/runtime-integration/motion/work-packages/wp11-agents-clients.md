# WP11 模型与外部客户端

状态：待实施。主责：Backend AI / CLI / MCP。前置：[WP07](./wp07-asset-capabilities.md)、[WP08](./wp08-host-slideshow-sync.md)、[WP09](./wp09-capture-export.md)、[WP10](./wp10-runtime-kit-editor.md)。

## 输入与落点

内置助手与 External API 继续共用代码规范。CLI/MCP 在同级独立仓实现适配，主仓维护其依赖的 Backend HTTP 契约与集成记录。

## 交付

- 扩展共用动画规范及 Runtime Kit 查询说明：先读 capability，再查真实资源动作，创建定义与绑定，等待 mutation job，按选择器取帧。
- 沿用 tool_specs 单一工具目录与 get_code_standards；只有参数契约变化时才修改工具规格，不另建动画工具清单。
- External API 支持动作摘要、新放映配置和临时 motionSnapshot，复用权限、幂等、版本与异步任务，不直连 Runtime 或泄露内部回执/票据。
- CLI/MCP 从 OpenAPI/能力摘要得到新参数，旧服务或关闭能力明确报不支持，不丢字段重试成旧行为。
- 为独立仓提供工作树/提交版本、生成类型基线、往返样例和失败样例；主仓通过不等于两个客户端已交付。
- 规范与示例覆盖 B01–B08，明确静态截图不能证明声音或动画播放，无法访问真实环境时不编造诊断结论。

## 验证与通过条件

同一受控测试工作空间分别由内置助手、CLI 与 MCP 查询/创建/修改/等待/取帧，核对最终对象版本、计划摘要、默认海报与临时截图。

覆盖关闭能力、旧 Schema、未知片段、过期引用与恢复；更新 OpenAPI/参数 Schema 时运行生成漂移及工具规格防漂移检查。

## 交接

将三种入口的完整证据和未交付项提交 WP12。用户自定义整类型规范保持原覆盖行为，不批量覆盖用户设置。

## 实施记录

- 主仓与 CLI/MCP 版本：待回填。
- 实际命令、通过/失败数量、Job 与可读产物：待回填。
- 未覆盖项：待回填。
