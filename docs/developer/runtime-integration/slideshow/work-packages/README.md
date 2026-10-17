# 自动放映工作包执行清单

状态：M0 实施中。WP01–WP11 已完成并提交；WP12 及 M1–M3 工作包待实施。本清单把原模块计划的 24 项上层工作拆为 33 个可交接的实施包；完成情况以各 WP 卡片为准。

## 1. 使用方式与完成规则

每包独立一页，包含主责、前置、修改范围、交付物、提交边界、验收编号和建议提交标题。领取时直接引用 WP 编号；通常一个包对应一个可评审 PR，跨仓包在对应客户端仓实施。

- 字段和行为只以[统一契约](../contract.md)为准，模块职责以[总计划](../README.md)和各模块计划为准。
- B/E/R/G/C 编号继续作为上层能力分组；执行进度以 WP 卡片为准，完成子包后再回填对应上层检查项。
- 卡片的前置表示开始实现所需的已交付输入；后置阶段验收不作为上游 Schema 包的前置，避免形成依赖环。
- 所有列出的前置均完成后才能将包转为可实施；纯 Schema/协议包可提前准备，但不能据此开放未验收能力。
- 状态按“待实施 → 实施中 → 待验收 → 完成”更新；缺外部输入时标明依赖待满足，不能把未验证项勾为完成。
- M0/M1/M2/M3 的出口分别为 WP12/WP21/WP30/WP33。出口包检查该阶段的兼容、产物和发布证据，单个 PR 合入不等于对应阶段支持承诺。
- 修改共享 Schema、生成文件或依赖锁时，由对应主责包统一交付，后续包消费该结果；不在多个包内各维护一份相同定义。

## 2. 工作包目录

### M0：配置与动画贯通（12 包）

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP01 冻结配置 Schema 与共享样例](./wp01-contract-fixtures.md) | Backend / 跨模块契约 | 无 |
| [WP02 模型列与双库迁移](./wp02-database-migration.md) | Backend | WP01 |
| [WP03 项目配置 CRUD 与样式隔离](./wp03-project-settings-api.md) | Backend | WP01、WP02 |
| [WP04 路由覆盖、继承与旧树保留](./wp04-route-overrides-api.md) | Backend | WP01、WP02、WP03 |
| [WP05 预览与构建快照下发](./wp05-artifact-build-config.md) | Backend / Runtime 构建接入 | WP03、WP04 |
| [WP06 模板包 schema 3 与三版本往返](./wp06-template-roundtrip.md) | Backend | WP03、WP04 |
| [WP07 External API、能力自省与类型生成](./wp07-external-api-codegen.md) | Backend / API 契约 | WP03、WP04、WP05 |
| [WP08 内容助手参数贯通](./wp08-ai-config-tools.md) | Backend / AI 工具 | WP03、WP04、WP07 |
| [WP09 Editor 项目放映表单](./wp09-editor-project-form.md) | Editor | WP03、WP07 |
| [WP10 Editor 逐路由覆盖与映射](./wp10-editor-route-form.md) | Editor | WP04、WP07、WP09 |
| [WP11 Runtime 参数消费与过渡完成信号](./wp11-runtime-transition-signals.md) | Runtime | WP01、WP05 |
| [WP12 M0 配置与动画联调门槛](./wp12-m0-integration.md) | 跨模块验证 / 发布 | WP06、WP08、WP10、WP11 |

### M1：单窗口定时放映（9 包）

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP13 单窗口放映状态机与时钟](./wp13-playback-state-machine.md) | Runtime | WP01 |
| [WP14 放映与静态执行上下文](./wp14-execution-contexts.md) | Runtime / Renderer 接入 | WP11 |
| [WP15 Router、页面就绪与调度桥接](./wp15-router-readiness-binding.md) | Runtime | WP05、WP11、WP13、WP14 |
| [WP16 单窗口入口、控制条与可见性](./wp16-playback-entry-controls.md) | Runtime / Editor | WP09、WP10、WP15 |
| [WP17 Renderer 禁推进与媒体静态帧](./wp17-renderer-static-media.md) | Renderer / 渲染契约 / Runtime 捕获 | WP05、WP14、WP15 |
| [WP18 PDF、PPTX 与打印的放映隔离](./wp18-export-isolation.md) | Runtime / 导出 | WP14、WP17 |
| [WP19 CLI 配置与路由往返](./wp19-cli-timer-settings.md) | web-presentation-cli | WP07 |
| [WP20 MCP 配置工具与往返](./wp20-mcp-timer-settings.md) | web-presentation-mcp | WP07 |
| [WP21 M1 单窗口联调与能力开放](./wp21-m1-integration-release.md) | 跨模块验证 / 发布 | WP12、WP16、WP17、WP18、WP19、WP20 |

### M2：媒体与演讲者自动放映（9 包）

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP22 媒体模式 Schema 与预览权限链](./wp22-media-schema-permissions.md) | Backend / Editor 预览桥 | WP21 |
| [WP23 活动页媒体注册与生命周期](./wp23-media-lifecycle.md) | Runtime / Runtime Kit 内部渲染器 | WP14、WP22 |
| [WP24 媒体结束翻页与受阻恢复](./wp24-media-end-advance.md) | Runtime | WP15、WP22、WP23 |
| [WP25 演讲者播放同步协议](./wp25-presenter-sync-protocol.md) | Runtime / Presenter | WP24 |
| [WP26 观众唯一调度与双窗口操作](./wp26-presenter-single-owner.md) | Runtime / Presenter | WP16、WP24、WP25 |
| [WP27 Editor 媒体模式配置](./wp27-editor-media-form.md) | Editor | WP09、WP10、WP22、WP24 |
| [WP28 CLI 媒体模式扩展](./wp28-cli-media-mode.md) | web-presentation-cli | WP19、WP22 |
| [WP29 MCP 媒体模式扩展](./wp29-mcp-media-mode.md) | web-presentation-mcp | WP20、WP22 |
| [WP30 M2 媒体、双屏与捕获回归](./wp30-m2-integration-release.md) | 跨模块验证 / Renderer / 发布 | WP21、WP22、WP24、WP26、WP27、WP28、WP29 |

### M3：长期无人值守增强（3 包）

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP31 长期放映入口与到期策略](./wp31-unattended-entry.md) | Backend / Runtime / 运维 | WP30 |
| [WP32 断网、防休眠与恢复清理](./wp32-unattended-recovery.md) | Runtime / 运维 | WP31 |
| [WP33 长稳演练与无人值守发布门槛](./wp33-unattended-soak-release.md) | 跨模块验证 / 运维 | WP31、WP32 |

## 3. 原模块计划对应关系

| 原工作项 | 实施包 |
| :--- | :--- |
| B01：Schema/存储 | WP01、WP02 |
| B02：项目/路由 API | WP03、WP04 |
| B03：预览与构建 | WP05 |
| B04：模板包 | WP06 |
| B05：External/AI/生成类型 | WP07、WP08 |
| B06：媒体扩展与授权 | WP22；能力开放在 WP30 |
| E01/E02：项目和路由表单 | WP09、WP10 |
| E03：单窗口入口 | WP16 |
| E04：媒体与双屏入口 | WP22、WP26、WP27 |
| R01：动画配置与完成信号 | WP11 |
| R02：调度与宿主 | WP13、WP15 |
| R03：上下文与操作区 | WP14、WP16；基础媒体禁播接入纳入 WP14 |
| R04：媒体生命周期与翻页 | WP23、WP24 |
| R05：双窗口协议与执行 | WP25、WP26 |
| R06：长期运行 | WP31、WP32、WP33 |
| G01：静态执行上下文 | WP14、WP15、WP17 |
| G02/G03：静态媒体/导出 | WP17、WP18 |
| G04：媒体下捕获与回收 | WP30 |
| C01：主仓接口交付 | WP07 |
| C02/C03：CLI/MCP | WP19、WP20 |
| C04：客户端媒体模式 | WP28、WP29 |

## 4. 建议开发与提交顺序

以下同一组中没有前置关联的包可分别开发和评审；表格只列输入已就绪时的分组，不代表已经开始执行。

| 阶段 | 顺序 |
| :--- | :--- |
| M0 | WP01 → WP02 → WP03 → WP04 →（WP05、WP06）→（WP07、WP11）→（WP08、WP09）→ WP10 → WP12 |
| M1 |（WP13、WP14、WP19、WP20）→ WP15 →（WP16、WP17）→ WP18 → WP21 |
| M2 | WP22 →（WP23、WP28、WP29）→ WP24 →（WP25、WP27）→ WP26 → WP30 |
| M3 | WP31 → WP32 → WP33 |

M0 最先实施 WP01。WP01 之后可提前开发 WP13 的纯状态机，但 Router/DOM 接入仍须等待 WP11/WP14，首期范围始终以当前阶段出口为准。配置契约和生成类型的变更先交付，再开展依赖它们的表单和客户端。

Backend 数据列/DTO、API 生成物、Runtime 配置结构、窗口同步协议分别由 WP01–WP07、WP07、WP11、WP25 负责。修改公共文件时保留其他工作包或用户的未提交改动，不顺手格式化无关文件。

## 5. 阶段出口核对

- WP12 对照[验收 A01–A08](../acceptance.md)：配置、迁移、旧客户端保护、模板、历史/构建与动画。
- WP21 对照[验收 A09–A17](../acceptance.md)：计时、手动介入、静态产物、客户端及单窗口能力开放。
- WP30 对照[验收 A18–A24](../acceptance.md)：媒体、权限、双屏唯一调度和 Renderer 生命周期。
- WP33 对照[长期运行专项](../acceptance.md)：目标部署的票据/网络/设备恢复和至少 60 分钟长稳。

每包必须记录实际测试命令、结果及未运行原因；UI、音视频、真实 PNG 和导出文件需要对应实机/产物证据。测试范围按 [dev-start-test 测试矩阵](../../../../../.agents/skills/dev-start-test/references/testing-matrix.md)选择，不为拆包新增一套测试命令。所有能力开放和部署动作在实施、验收阶段另行执行。
