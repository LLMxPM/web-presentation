# Runtime Kit 契约

Runtime Kit 是页面源码、工作空间组件源码和 previewSchema 可以引用的公共能力集合。

## manifest

公开能力以 `runtime/src/runtime-kit/manifest/runtime-kit.manifest.json` 为单一事实源。Backend 通过该清单校验页面源码、组件源码和 previewSchema 的导入边界。

## 命名规则

- 清单项名称必须使用 `<ExportName>.v<整数版本>`。
- 公开 import path 必须带 `.vN`。
- 不兼容演进时新增 v2/v3 文件，不修改仍被依赖的旧版本文件。

## 禁止暴露

Runtime shell 内部组件、component-preview 宿主页、PDF 导出、侧栏、缩略图、Toast、ErrorBoundary 等壳层能力不应通过 Runtime Kit 暴露给页面源码、组件源码或 AI 能力目录。

## 测试要求

Runtime Kit manifest 或公开 import path 变化时，应补充 Runtime manifest 测试和根仓 Backend 契约测试。
