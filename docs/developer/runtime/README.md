# Runtime 开发文档

本目录面向在 `runtime/` 中开发页面、组件和 Runtime Kit 能力的维护者。服务启动和测试入口见[本地开发指南](../getting-started.md)；Backend、Renderer 与 Runtime 之间的协议见[Runtime 接入文档](../runtime-integration/README.md)。

## 页面与公共能力

| 文档 | 内容 |
| :--- | :--- |
| [页面添加指南](./page-creation-guide.md) | 页面源码、画布与本地开发流程 |
| [页内动画与减少动态效果](./page-animation-guide.md) | 动效能力、静态基线、偏好适配、排查与模型提示入口 |
| [路由配置指南](./routes-config-guide.md) | fixture 路由与页面入口配置 |
| [主题系统使用指南](./theme-usage-guide.md) | 主题变量与页面样式 |
| [图标系统使用指南](./icon-system-guide.md) | 图标配置与页面引用 |
| [Runtime Kit 能力说明](./runtime-kit-capabilities.md) | 公开能力目录、版本和使用边界 |

## 组件

| 文档 | 内容 |
| :--- | :--- |
| [组件预览 previewSchema 指南](./components/component-preview-schema-guide.md) | 组件预览输入与场景 |
| [Connector 连接线组件](./components/connector.md) | DOM 连线能力和约束 |
| [目录能力使用说明](./components/table-of-contents-guide.md) | 演示文稿目录组件 |

## Runtime 内部接入细节

| 文档 | 内容 |
| :--- | :--- |
| [SaaS 运行时架构与时序](./integration/runtime-architecture.md) | 预览上下文与运行时边界 |
| [页内动画三维动作与媒体编排首期规划](../runtime-integration/motion/README.md) | 统一播放控制、媒体时钟、模型动作与静态采样；含契约和工作包，待实施 |
| [翻页动画与自动放映 Runtime 计划](../runtime-integration/slideshow/runtime.md) | 过渡完成信号、计时调度、媒体生命周期、双窗口和禁播上下文；待实施 |
| [鉴权与安全契约](./integration/auth-and-security.md) | 令牌、访问范围与安全约束 |
| [Backend 对接 API](./integration/backend-api.md) | Runtime 消费的 Backend 接口 |
| [Preview Artifact 规范](./integration/release-artifact-spec.md) | 预览产物结构 |
| [Vue 页面资源引用规范](./integration/asset-usage-guide.md) | 资源 URL 与特殊格式渲染 |
| [三维资源复用与 Three.js 渲染接入分析](../runtime-integration/threejs-rendering-and-management-analysis.md) | GLB/glTF Viewer、实例视角、首帧、依赖加载与静态导出的拟议接入方案 |
| [三维资源复用与渲染实施计划](../runtime-integration/threejs-resource-implementation-plan.md) | 标准 Viewer、多实例、首帧、静态导出与构建的工作包和验收门槛 |
| [PPTX 导出 DOM 契约](./integration/pptx-export-dom-contract.md) | 表格、媒体与连接线的显式导出属性、版本约定与识别优先级 |
| [PPTX 导出升级规划](./pptx-export-upgrade-plan.md) | 已核实缺陷、分阶段工作包、页面采集与视觉映射边界、性能和产物验收 |

Runtime 服务自身的运行命令与目录概览见 [runtime/README.md](../../../runtime/README.md)。
