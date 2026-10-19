# Runtime 接入文档

Runtime 接入文档说明平台如何组织和调用 `runtime/` 服务，以及页面源码、组件源码、previewSchema、构建产物和配置模板之间的契约。

## 文档导航

| 文档 | 内容 |
| :--- | :--- |
| [运行时开发与维护](./runtime-workflow.md) | Runtime 本地开发、质量门禁、契约验证与构建部署 |
| [翻页动画与自动放映实施计划](./slideshow/README.md) | 项目与路由配置、Backend/Editor/Runtime/Renderer、CLI/MCP 和分阶段验收；待实施 |
| [音频资源、页面旁白与交互音效实施计划](./audio/README.md) | `audio` 资源、`AssetAudio.v1`、旁白生命周期、切页/点击 cue、静态执行隔离和 20 个工作包；待实施 |
| [用户文件存储鉴权与缓存实施规划](./file-storage-auth-cache-plan.md) | 当前文件读取链路、artifact 与任务授权、缓存和存储边界、12 个工作包及发布验收；待实施 |
| [页面校验截图复用与智能体引导优化计划](./page-validation-screenshot-agent-guidance-plan.md) | 能力与图标发现、入口恢复提示、联合渲染、候选截图发布、缓存及 CLI/MCP 验收；待实施 |
| [Runtime Kit 契约](./runtime-kit-contract.md) | manifest 命名、版本化 import path 和 Backend 校验 |
| [previewSchema 契约](./preview-schema.md) | 组件预览 schema 的能力边界和校验要求 |
| [三维资源复用与 Three.js 渲染接入分析](./threejs-rendering-and-management-analysis.md) | 标准资源、渲染器与引用实例的边界，GLB/glTF 管理、快照与分发；当前为设计分析 |
| [三维资源复用与渲染实施计划](./threejs-resource-implementation-plan.md) | M0/M1/M2、接口与历史绑定、14 个工作包、依赖顺序及发布验收；待实施 |
| [组件 Check 体系设计](./component-code-check-design.md) | 当前 contract/compile 校验与历史浏览器方案的边界 |
| [页面可视化编辑契约](./page-visual-edit.md) | Backend 源码权威、编辑态 artifact、SFC 节点映射与受限回写协议 |
| [富文本源码范围定位加固计划（已归档）](../../archive/architecture-2026-09/reports/rich-text-source-range-hardening-plan.md) | 历史修复设计；现有实现的交互验证由现行计划 M08 承接 |
| [构建产物规格](./release-artifact-spec.md) | Runtime 构建产物与 Backend 托管关系 |
| [配置模板边界](./config-templates.md) | Backend 配置模板和 Runtime fixture 配置的边界 |

## 外部文档

Runtime 自身能力、开发方式和内部实现见 [runtime/README.md](../../../runtime/README.md) 以及 [docs/developer/runtime/](../runtime/)。
