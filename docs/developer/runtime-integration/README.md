# Runtime 接入文档

这里记录 Backend、Editor、Renderer 与 Runtime 之间当前生效的协议和开发入口。Runtime 内部页面、组件和公共能力的使用方法见[Runtime 开发文档](../runtime/README.md)。

| 任务 | 现行文档 |
| :--- | :--- |
| 新增页面或 Runtime Kit 公共能力 | [Runtime Kit 契约](./runtime-kit-contract.md)、[Runtime Kit 能力说明](../runtime/runtime-kit-capabilities.md) |
| 修改放映配置或播放 | [放映接入](./slideshow/README.md)、[放映契约](./slideshow/contract.md) |
| 修改音频资源、旁白或 cue | [音频接入](./audio/README.md)、[音频契约](./audio/contract.md) |
| 修改预览或构建 | [预览源站与 artifact](./preview/README.md)、[构建产物规格](./build-artifact-spec.md)、[配置模板边界](./config-templates.md) |
| 修改组件预览或校验 | [previewSchema 契约](./preview-schema.md)、[组件源码校验](./component-code-check.md) |
| 维护 Runtime 服务 | [Runtime 开发与维护](./runtime-workflow.md)、[Runtime 开发文档](../runtime/README.md) |
| 修改受限可视化编辑 | [页面可视化编辑契约](./page-visual-edit.md) |

跨服务实施计划与待验收项集中在[专题工作目录](../projects/README.md)，已结束的放映工作包、审查和验收记录集中在[开发过程归档](../../archive/developer-work-2026-10/README.md)。
