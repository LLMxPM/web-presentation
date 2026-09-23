# Runtime 开发文档

本目录面向在 `runtime/` 中开发页面、组件和 Runtime Kit 能力的维护者。服务启动和测试入口见[本地开发指南](../getting-started.md)；Backend、Renderer 与 Runtime 之间的协议见[Runtime 接入文档](../runtime-integration/README.md)。

## 页面与公共能力

| 文档 | 内容 |
| :--- | :--- |
| [页面添加指南](./page-creation-guide.md) | 页面源码、画布与本地开发流程 |
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
| [鉴权与安全契约](./integration/auth-and-security.md) | 令牌、访问范围与安全约束 |
| [Backend 对接 API](./integration/backend-api.md) | Runtime 消费的 Backend 接口 |
| [Preview Artifact 规范](./integration/release-artifact-spec.md) | 预览产物结构 |
| [Vue 页面资源引用规范](./integration/asset-usage-guide.md) | 资源 URL 与特殊格式渲染 |

Runtime 服务自身的运行命令与目录概览见 [runtime/README.md](../../../runtime/README.md)。
