# WP25：演讲者播放同步协议

状态：已完成（2026-10-18）。阶段：M2。主责：Runtime / Presenter。
上层工作项：R05（协议）；详见[模块计划](../runtime.md)。本包是该工作项的实施拆分，不是另一份配置契约。

## 前置与输入

前置完成：[WP24](./wp24-media-end-advance.md)。
字段与行为以[统一契约](../contract.md)为准；所有依赖编号见[执行清单](./README.md)。

## 修改范围与交付

- 修改范围：扩展 BroadcastChannel/localStorage 消息与纯处理逻辑：协议版本、频道/产物、owner epoch、命令 ID、revision、路径/状态/剩余时间。
- 交付物：可去重、拒绝旧 owner 和恢复快照的双窗口同步协议与处理器。
- 提交边界：先完成协议与状态应用，不在此启动第二个调度器或依赖真实窗口做纯逻辑测试。

## 完成标准

- [x] 实现及评审覆盖上述修改范围，未超出提交边界。
- [x] 行为验收：重复/过期/身份不匹配消息不改变状态；新窗口可重新建立本地时钟基准；不比较跨窗口 performance.now。
- [x] 验证范围：纯协议解析、去重/乱序/身份与 storage 兜底测试；真实双窗口在 WP26 验收。
- [x] 关联验收：A21、A22 的协议侧；真实窗口一致性与失效交接见 WP26。
- [x] 记录代码版本、实际测试命令/结果、未运行项及原因，产物保存到任务专属临时目录。
- [x] 回填本卡状态与证据；阶段能力是否开放由对应阶段出口包决定，单包完成不等于整阶段交付。

建议提交标题：`WP25：演讲者播放同步协议`。通常按一个可评审 PR 实施；若实际改动仍过大，先按输入/输出再拆子包，保留父编号和依赖。

## 实施记录（2026-10-18）

- 协议：新增 `presenter-sync-protocol.ts`，v2 信封包含 `protocol`、`channelId`、产物身份、`sourceId`、`ownerEpoch`、递增 `revision`、`eventId` 与可选 `commandId`；state-sync/navigate 携带完整路径、视图、tileSize 与播放快照（状态、剩余毫秒、delay、媒体等待、页码）。
- 处理器：Receiver 在业务应用前完成协议/身份/self/频道/产物校验，按 event 与 command 去重，维护 owner epoch 水位与 per-source revision；新 owner 接管后旧 owner 的消息失效。
- 时钟：接收方只用本地到达时间加 `remainingMs` 计算 deadline，不跨窗口比较 `performance.now`；新观众 `ready` 后控制台回发状态快照。
- 集成：控制器所有 BroadcastChannel 与 storage 消息统一走 Receiver；storage 初始导航升级为 v2；暴露 `playbackSnapshot`/`remotePlayback`/`updatePlayback` 供 WP26 消费。WP26 在 v2 信封追加 `role` 并按角色隔离 owner 水位，观众窗口只接受控制台来源的导航。
- 验证：定向 12 passed；Runtime 全量 141 files/1081 passed/3 skipped；`pnpm --dir runtime check` 与改动文件 ESLint 通过。
- 未运行：真实双窗口调度权交接与播放器应用（WP26）；生产 OAuth 无关。
- 产物：`.tmp/wp25/`。
- 提交：`61d1457`。

测试环境与命令选择遵循 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md)，不因执行本卡重复启动服务或重置开发数据。
