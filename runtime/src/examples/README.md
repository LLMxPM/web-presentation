<!-- 文件功能：说明 Runtime 示例目录的分层规则，区分可供外部参考的示例与仅服务本地启动的示例。 -->
# Runtime 示例目录

`src/examples` 统一收纳 Runtime 仓库内的示例代码，避免示例页面散落在运行时入口目录中。

## 目录约定

- `public/`：对外示例，面向平台工作空间组件、文档和接入方参考。这里的代码应优先只依赖 `@runtime-kit` 公开能力，避免引用 Runtime shell 私有模块。
- `local/`：本地示例，仅用于 `pnpm dev` 默认 fixture 配置和 Runtime 壳层调试。这里可以引用 Runtime 内建资源，但不作为外部工作空间源码模板。

## 当前示例

- `public/component-preview/PreviewSchemaDemoCard.vue`：组件预览 `previewSchema` 的外部参考示例。
- `local/views/defaultpage/`：本地 fixture 首页、目录页、结束页等演示页面。
- `local/views/feature-showcase/`：本地 Runtime Kit 能力展示页面。

## 维护规则

- 新增对外文档示例时放入 `public/`，并优先保持依赖面接近真实工作空间源码。
- 新增仅服务 Runtime 本地调试的页面时放入 `local/views/`，并在 `public/config/routes.config.yaml` 中使用 `@/examples/local/views/...` 引用。
- `src/views` 只保留 Runtime 的路由入口视图，例如整页预览和组件预览入口，不再放置演示页面。
