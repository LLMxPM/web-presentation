# Runtime Kit 契约

Runtime Kit 是页面源码、工作空间组件源码和 previewSchema 可以引用的公共能力集合。

## manifest

公开能力以 `runtime/src/runtime-kit/manifest/runtime-kit.manifest.json` 为单一事实源。Backend 通过该清单校验页面源码、组件源码和 previewSchema 的导入边界。

## 命名规则

读取能力时完整保留 `import_path`、`usage`、`constraints`、`preview_schema.props`，按字段投影，不按 JSON 字符数截断。字段缺失或出现省略标记时补读详情。

`Icon.v1` 是渲染契约，平台图标名称来自当前工作空间 active 图标资源；`home` 等示例不保证存在。先查询真实资源并保留分页，再读取契约；没有合适资源时按任务授权创建 SVG 图标，使用返回的真实 `name`。独立 Runtime 仍可使用自身图标配置。

- 清单项名称必须使用 `<ExportName>.v<整数版本>`。
- 公开 import path 必须带 `.vN`。
- 不兼容演进时新增 v2/v3 文件，不修改仍被依赖的旧版本文件。

## 禁止暴露

Runtime shell 内部组件、component-preview 宿主页、PDF 导出、侧栏、缩略图、Toast、ErrorBoundary 等壳层能力不应通过 Runtime Kit 暴露给页面源码、组件源码或 AI 能力目录。

## 测试要求

Runtime Kit manifest 或公开 import path 变化时，应补充 Runtime manifest 测试和根仓 Backend 契约测试。
