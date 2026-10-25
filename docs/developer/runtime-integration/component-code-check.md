# 组件源码校验

本文记录当前组件自动校验边界。包含浏览器 preset、真实渲染与布局检查的旧方案见[设计归档](../../archive/developer-work-2026-10/component-code-check-design.md)，该阶段当前未启用。

## 当前行为

- 组件创建、源码修改，以及修改 `preview_schema` 或 `component_type` 的操作进入组件外部任务；名称、摘要等轻量元数据保持同步路径。
- 自动校验执行组件契约与 Runtime 编译检查，不运行浏览器真实渲染、preset 场景或布局检查。用户仍可在组件预览页手动检查视觉结果。
- Backend 保留完整内部诊断；模型侧写入结果与 `validate_entity` 返回有界精简文本。需要细节时，使用相同目标和候选 mode 调用 `validate_entity(detail=true)`。
- previewSchema 的结构以 Backend 的 `component_preview_schema.v1.json` 为事实源；可导入能力还须通过 Runtime Kit manifest 与工作空间组件边界校验。

修改组件校验时，核对[previewSchema 契约](./preview-schema.md)、[AI 工具规格](../backend/ai-tool-specs.md)、[`component_preview_schema.v1.json`](../../../backend/app/core/component_preview_schema.v1.json)与共享正反例。不要把归档中的浏览器诊断阶段写成当前自动执行链路。
