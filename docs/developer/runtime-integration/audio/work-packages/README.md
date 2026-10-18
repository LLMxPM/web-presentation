# 音频工作包执行清单

状态：WP01–WP02 已完成；WP03–WP05 已实现，等待 WP06 真机验收；WP07–WP11 已实现，等待 WP12 联调与能力开放；WP13–WP17 已实现，WP18–WP20 待实施。共 20 个工作包，M0/M1/M2 出口分别为 WP06、WP12、WP20。

## 1. 使用方式

每个工作包应对应一个可独立评审的提交或 PR。领取工作时引用 WP 编号，完成后在卡片中回填代码版本、测试命令、结果和未运行项。

- 字段、默认值和运行行为只以[统一契约](../contract.md)为准。
- 前置表示开始实现所需输入，不表示可以跳过本包自己的测试。
- 状态按“待实施 → 实施中 → 待验收 → 完成”更新。
- 修改 OpenAPI、Runtime Kit manifest、模板包 Schema 或数据库时，由指定工作包维护唯一变更，后续包只消费。
- 单包合入不开放阶段能力；只有出口包完成并满足[验收计划](../acceptance.md)后才更新 capability 和用户文档。
- 实际测试选择遵循 [`dev-start-test`](../../../../../.agents/skills/dev-start-test/SKILL.md)，不在每张卡复制服务命令。

## 2. M0：音频资源基线

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP01 冻结音频契约与共享样例](./wp01-contract-fixtures.md) | Backend / 跨模块契约 | 无 |
| [WP02 Backend 音频资源类型与读取链路](./wp02-backend-audio-assets.md) | Backend | WP01 |
| [WP03 Editor 音频资源管理与试听](./wp03-editor-audio-assets.md) | Editor | WP01、WP02 |
| [WP04 Runtime Kit `AssetAudio.v1`](./wp04-runtime-kit-asset-audio.md) | Runtime Kit | WP01、WP02 |
| [WP05 引用、artifact、构建与包往返](./wp05-artifact-packages-references.md) | Backend / Runtime 构建 | WP02、WP04 |
| [WP06 M0 音频资源联调门槛](./wp06-m0-integration.md) | 跨模块验证 / 发布 | WP03、WP04、WP05 |

M0 只开放手动内容音频。`purpose="narration"` 可以进入类型/manifest，但 capability 在 M1 出口前不得宣称可自动播放。

## 3. M1：页面旁白

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP07 媒体用途与活动页会话](./wp07-media-purpose-session.md) | Runtime | WP04、WP06 |
| [WP08 旁白开始与页面生命周期](./wp08-narration-lifecycle.md) | Runtime | WP07 |
| [WP09 `media_end` 聚合与错误恢复](./wp09-media-end-errors.md) | Runtime | WP07、WP08 |
| [WP10 静音、双窗口与静态隔离](./wp10-mute-presenter-static.md) | Runtime / Renderer / 导出 | WP08、WP09 |
| [WP11 Editor 与 AI 旁白创作约束](./wp11-editor-ai-narration.md) | Editor / Backend AI | WP08、WP09 |
| [WP12 M1 页面旁白联调门槛](./wp12-m1-integration.md) | 跨模块验证 / 发布 | WP10、WP11 |

## 4. M2：切页与点击音效

| 工作包 | 主责 | 前置 |
| :--- | :--- | :--- |
| [WP13 项目音频设置与 cue 绑定存储](./wp13-audio-settings-storage.md) | Backend | WP01、WP06 |
| [WP14 cue 快照、构建、模板与引用](./wp14-cue-snapshot-packages.md) | Backend / Runtime 构建 | WP05、WP13 |
| [WP15 Runtime `AudioCueEngine`](./wp15-audio-cue-engine.md) | Runtime shell | WP14 |
| [WP16 切页开始事件与方向 cue](./wp16-transition-cues.md) | Runtime transitions | WP15 |
| [WP17 `useAudioCue.v1` 与点击 cue](./wp17-interaction-composable.md) | Runtime Kit / Runtime shell | WP15 |
| [WP18 Editor 项目音频设置](./wp18-editor-audio-settings.md) | Editor | WP13、WP14 |
| [WP19 External API、CLI 与 MCP](./wp19-external-clients.md) | Backend / CLI / MCP | WP13、WP14 |
| [WP20 M2 音效联调与发布门槛](./wp20-m2-integration.md) | 跨模块验证 / 发布 | WP16、WP17、WP18、WP19 |

## 5. 依赖主链

```text
WP01 → WP02 ─┬→ WP03 ───────────────┐
             ├→ WP04 → WP05 ───────┤→ WP06
             │                      │
             └──────────────────────┘

WP06 → WP07 → WP08 → WP09 → WP10 ─┐
                        └→ WP11 ────┴→ WP12

WP06 → WP13 → WP14 → WP15 ─┬→ WP16 ─┐
                            └→ WP17 ─┤
                 WP14 ───────→ WP18 ├→ WP20
                 WP14 ───────→ WP19 ┘
```

WP03 与 WP04 可并行；WP10 与 WP11 在 WP09 后可并行；WP16–WP19 可在共同输入完成后并行。热点文件冲突仍应按[实施计划](../implementation-plan.md)中的顺序协调。

## 6. 完成定义

每包至少满足：

- 实现和测试未超出卡片提交边界。
- 新增源文件有文件功能说明，函数有中文职责/约束注释。
- 修改契约时生成物、正反例和防漂移测试同步。
- UI 改动符合 `DESIGN.md`，媒体行为有真实浏览器证据。
- 不覆盖用户未提交改动，不提交缓存、依赖、构建产物或无授权音频。
- 卡片状态、证据和阶段限制已回填。
