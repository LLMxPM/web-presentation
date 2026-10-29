# 音频后续验收与增强

`audio_assets`、`page_narration` 和 `audio_cues` 已默认开放。当前字段与播放行为见[音频接入](../../runtime-integration/audio/README.md)和[统一契约](../../runtime-integration/audio/contract.md)。原 M0–M2 计划及 20 个工作包已移至[实施过程归档](../../../archive/developer-work-2026-10/audio/plan.md)。

## 仍需处理

| 事项 | 下一步 |
| :--- | :--- |
| 原阶段验收矩阵 | 按[验收清单](./acceptance.md)继续核对未覆盖的格式、浏览器与旁白生命周期场景；已有 Chromium 证据见[动画前联合验收](../../../archive/developer-work-2026-10/pre-motion-joint-acceptance.md) |
| External 资源引用与页面资源依赖 | 原改造计划 E01，独立确定接口与权限后实施 |
| 音频时长与版本元数据 | 原改造计划 E02，先冻结可验证的数据来源与响应语义 |
| External 构建任务创建、查询和等待 | 原改造计划 E03b，作为独立专题立项，不并入音频验收 |

E01、E02、E03b 的原始背景与已完成批次见[CLI 实测复核归档](../../../archive/developer-work-2026-10/audio/cli-dev-environment-remediation-plan.md)。`feature/motion` 分支承接尚未合入的播放收敛；本目录不复制该分支的过程记录。MCP 不在当前交付范围。
