<!-- 文件功能：说明 Runtime 示例目录的分层规则，区分可供外部参考的示例与仅服务本地启动的示例。 -->
# Runtime 示例目录

`src/examples` 统一收纳 Runtime 仓库内的示例代码，避免示例页面散落在运行时入口目录中。

## 目录约定

- `public/`：对外示例，面向平台工作空间组件、文档和接入方参考。这里的代码应优先只依赖 `@runtime-kit` 公开能力，避免引用 Runtime shell 私有模块。
- `local/`：本地示例，仅用于 `pnpm dev` 默认 fixture 配置和 Runtime 壳层调试。这里可以引用 Runtime 内建资源，但不作为外部工作空间源码模板。

## 本地能力示例

`local/views/feature-showcase/` 按 manifest 的 `category` 分章组织，配合 `index` 总览页对外呈现全部公开能力：

```
local/
├── components/ShowcasePage.vue   示例页统一骨架：标题 + 本页能力 + 示例区
└── views/feature-showcase/
    ├── Index.vue                 能力总览：直接读取 runtime-kit.manifest.json 生成能力矩阵
    ├── page/                     页面与路由
    │   ├── CanvasShowcase.vue    DefaultContainer / usePageSize / buildPageCanvasStyle
    │   └── RoutingShowcase.vue   useCurrentPage / useRouteCatalog / usePageNavigation
    ├── runtime/                  运行时能力
    │   ├── ThemeShowcase.vue     useTheme / resolveColor
    │   ├── IconShowcase.vue      Icon / ThemeLogo
    │   ├── DataTableShowcase.vue DataTable
    │   ├── ConnectorShowcase.vue Connector
    │   └── SceneShowcase.vue     usePageScene / useStaticPresentation / createSceneMediaTask
    └── assets/                   资源渲染
        ├── ImageShowcase.vue     AssetImage / useAssetSrc / useAssetBackground / resolveResourcePath
        ├── VideoShowcase.vue     AssetVideo
        ├── AudioShowcase.vue     AssetAudio / useAudioCue
        ├── ChartShowcase.vue     AssetChart
        ├── MermaidShowcase.vue   AssetMermaid
        ├── DrawioShowcase.vue    AssetDrawio
        ├── FormulaShowcase.vue   AssetFormula
        └── ModelShowcase.vue     AssetModel（契约说明）
```

约定：

- 示例页优先使用 manifest 中的公开导入路径；只有本地 fixture 无法提供工作空间资源清单时（音频播放器、三维直连），才在 `ShowcasePage` 的能力标签上标注「本地直连」。
- 资源类示例在没有工作空间资源时用 `fallback` 传入本地 URL，并在页面上说明平台页面应传 `name`。
- 新增能力时先更新 `runtime-kit.manifest.json`，再补充示例页并登记到 `Index.vue` 的能力矩阵。

## 其他示例

- `public/component-preview/PreviewSchemaDemoCard.vue`：组件预览 `previewSchema` 的外部参考示例。
- `local/views/defaultpage/`：本地 fixture 首页、目录页、结束页等演示页面。
- `public/model/`：本地三维示例 GLB（Box、Box Animated、Rigged Figure、Fox、Robot Expressive），来源与授权见 [`public/model/ATTRIBUTION.md`](../../public/model/ATTRIBUTION.md)，仅用于三维示例页渲染。

## 维护规则

- 新增对外文档示例时放入 `public/`，并优先保持依赖面接近真实工作空间源码。
- 新增仅服务 Runtime 本地调试的页面时放入 `local/views/`，并在 `public/config/routes.config.yaml` 中使用 `@/examples/local/views/...` 引用。
- `src/views` 只保留 Runtime 的路由入口视图，例如整页预览和组件预览入口，不再放置演示页面。
