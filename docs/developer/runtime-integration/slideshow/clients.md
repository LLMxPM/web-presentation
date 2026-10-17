# CLI、MCP 与 External API 对接计划

状态：主仓 External API M0 已实现并通过 WP12 验收；CLI/MCP 命令（WP19/WP20）待实施。本文件维护主仓交付边界与跨仓工作包；CLI 和 MCP 的具体命令、工具及客户端实现分别在独立仓维护，不假定其当前已支持放映参数。

实施拆分见[工作包执行清单](./work-packages/README.md)：WP07 主仓接口、WP19 CLI、WP20 MCP、WP28/WP29 两仓媒体扩展。各客户端包在对应仓内独立提交，以下 C 编号保留为上层职责。

字段、权限、HTTP 路径及省略/null 语义以[统一契约](./contract.md)为准；现有公开边界参见 [External API v1](../../reference/external-agent-api.md)。

## 1. 主仓交付：C01（M0，依赖 B02/B05）

- [ ] 扩展项目创建、详情、PATCH、configuration 读写与 route-tree DTO，共用 Backend Schema 和业务服务。
- [ ] capabilities 的 `slideshow` 对象与 OpenAPI 披露放映支持范围；源码 standards 不复制项目配置 Schema；M0/M1 不宣传 `media_end` 和双窗口自动放映。
- [ ] 交付可直接测试的完整请求/响应正反例：项目默认、逐页覆盖、恢复继承、未知模式、越界时间和权限失败。
- [ ] 明确幂等键对省略/null 的不同指纹及重试结果；不能把配置写入当作页面源码变更任务。
- [ ] Gateway 真实入口对齐 OpenAPI、权限、错误码和请求体；不以 Backend 直连成功代替 Gateway 验证。
- [ ] 主仓规范文档更新后向客户端仓提供字段映射和验收清单；具体跨聊发送或外部通知仅在用户明确授权时执行。

交付物：已实现且通过契约测试的 API、能力信息、样例和兼容说明。客户端开发以这些事实为输入，不能仅根据本计划猜测新接口可用。

## 2. CLI：C02（M1，依赖 C01）

责任仓：[web-presentation-cli](https://github.com/LLMxPM/web-presentation-cli)。

- [ ] 更新独立同步 API Client 的项目配置、路由节点与响应解析，能保留新增字段和显式 null。
- [ ] 现有配置/路由命令支持放映对象或结构化文件输入；具体命令与参数名由 CLI 仓对照既有命令体系制定，不在主仓复制命令清单。
- [ ] 读取→修改排序或标题→整树写回时携带原始覆盖，过滤只读生效值；恢复继承必须发送 null。
- [ ] 配置失败按 Backend 原始字段错误返回；旧服务不支持时明确提示能力缺失，不能写 Runtime fixture 或本地文件冒充平台成功。
- [ ] 更新配套 Skill 的放映配置流程，说明项目默认、路由覆盖和运行时开始播放的边界；配置成功不等于已控制用户浏览器播放。
- [ ] 客户端仓补充 Schema、序列化、幂等重试及旧服务兼容测试，维护该仓实施与发布文档。

验收：CLI 写项目默认，Editor 可读取；Editor 设置逐页覆盖，CLI 修改路由排序后不丢配置；旧 Backend 明确失败。

## 3. MCP：C03（M1，依赖 C01）

责任仓：[web-presentation-mcp](https://github.com/LLMxPM/web-presentation-mcp)。

- [ ] 更新独立异步 API Client 及项目/路由相关 Tool Schema、Resource 展示和返回摘要，复用服务端约束。
- [ ] 区分“保存放映配置”与“操纵正在运行的浏览器”；本期 Tool 只写业务配置，不新增跨设备播放控制协议。
- [ ] 参数 Schema 显式表达完整项目对象、可空路由组和只读生效值，避免模型把继承值展开后永久覆盖。
- [ ] 保持用户授权、工作空间隔离、Scope 和幂等处理；参数错误不得通过自由文本或无约束字典旁路发送。
- [ ] 补充真实 Backend/Gateway 的协议适配测试及失败输出，更新 MCP 仓工具文档和发布兼容范围。

验收：MCP、CLI 和 Editor 对相同放映参数得到相同结果；MCP 改排序不丢显式覆盖，跨工作空间访问失败。

## 4. M2 能力扩展：C04（依赖 B06/R04/R05）

- [ ] 客户端根据服务端能力开放 `media_end` 和超时字段，完整往返升级后的 `advance` 对象。
- [ ] 更新样例和 Skill/Tool 说明，明确循环媒体不参与等待、播放受阻需观众窗口操作。
- [ ] 兼容 M1 服务：不能发送其不认识的扩展字段或把未支持模式降级成其它模式后返回成功。

## 5. 发布次序

先完成 Backend 与 Runtime 对应阶段能力，再更新客户端；Editor 与 Backend/Runtime 版本应配套部署。客户端仓可独立发布，但发布说明必须标明所需服务端能力，跨仓验收证据归入[验收计划](./acceptance.md)，不把尚未交接的工作标为完成。
