# PPTX 导出 DOM 契约

Runtime 的可编辑 PPTX 导出会把页面 DOM 转换成 PowerPoint 原生图元。转换发生在**浏览器已经渲染完成之后**，转换器只能读取 DOM，拿不到 Vue 组件实例、props 或样式来源。因此「这个节点是什么」必须写在 DOM 上。

本文档定义 Runtime Kit 组件为此打出的**显式导出 DOM 契约**：带版本、与样式解耦的 `data-runtime-kit-*` 属性。契约的存在意义是把「组件长什么样」和「导出器如何识别组件」分开——调整 viewer 样式类名不应该弄坏 PPTX 导出。

## 为什么不用样式类名

历史上媒体识别依赖 `.mermaid-viewer`、`.image-viewer` 这类样式类名，连接线识别依赖 `.connector-svg`。同一个类名同时承担**样式**和**导出识别**两个职责，导致：

- 重构 viewer 样式或改用 Tailwind 工具类时，会静默破坏导出，且没有测试拦得住。
- 类名没有版本，无法表达「识别规则变了」。
- 契约只活在代码里，组件作者不知道哪些类名是承重的。

现在识别一律**显式契约优先、样式类名兜底**。类名兜底是永久保留的回退路径，用于覆盖历史页面源码、第三方组件和尚未声明契约的节点，不是待删除的过渡代码。

## 版本编码约定

所有契约属性统一采用「**属性名承载语义，属性值只承载版本**」的形式：

```html
<div data-runtime-kit-table="v1">          <!-- 版本 -->
  <div data-runtime-kit-table-cell="v1"    <!-- 版本 -->
       data-row-index="0"                  <!-- 语义载荷 -->
       data-column-index="1"></div>
</div>
```

媒体契约沿用同一形状，把类型作为独立的语义载荷属性：

```html
<div data-runtime-kit-media="v1" data-runtime-kit-media-kind="mermaid"></div>
```

选择这种编码而不是 `data-runtime-kit-media="mermaid.v1"` 这类复合取值，理由：

1. **与既有表格契约同形**。表格契约已经是「标记属性取值只有版本 + 独立属性承载载荷」，媒体契约照此办理，两套契约读起来一致。
2. **版本门禁是一次精确字符串比较**，不需要解析。消费端写 `getAttribute(...) === 'v1'`；复合取值需要 split，还要约定哪一段是版本。
3. **选择器可以精确匹配**。`[data-runtime-kit-media="v1"]` 是合法精确选择器；复合取值只能退化成 `^=` 前缀匹配，无法表达「任意已知版本」。
4. **未知版本安全失败**。节点标记为 `v2` 时消费端直接判定「未声明契约」，落到类名兜底，而不是解析出一个半新半旧的结果。表格契约对假想的 `v2` 也是同样语义。
5. **演进粒度清晰**。新增一个媒体类型是纯词汇表扩充，不动版本；改变某个类型的**含义**或它要求的伴随属性，才是版本升级。复合取值会把这两件事混在一个字符串里。

版本升级方式：新增 `v2` 取值并在消费端并列支持，生产者按页面源码兼容性择一输出；不要就地改写 `v1` 的语义。

## 契约一览

| 契约 | 标记属性 | 载荷属性 | 生产者 | 消费者 |
| :--- | :--- | :--- | :--- | :--- |
| 表格 | `data-runtime-kit-table` | — | `DataTable.v1.vue` 根节点 | `PPTXDomConverterTable` |
| 表格单元格 | `data-runtime-kit-table-cell` | `data-row-index`、`data-column-index` | `DataTable.v1.vue` 单元格 | `PPTXDomConverterTable` |
| 媒体 | `data-runtime-kit-media` | `data-runtime-kit-media-kind` | 7 个 internal viewer 根节点 | `PPTXDomConverterMedia`、`PPTXDomConverterRaster` |
| 三维静态帧 | `data-runtime-model-frame` | — | `model-static-frames.ts` prepare 阶段 | `PPTXDomConverterMedia` |
| 连接线 | `data-runtime-kit-connector` | — | `Connector.v1.vue` 根 `<svg>` | `svg/ConnectorTightBounds` |

媒体契约的读取实现集中在 `runtime/src/core/services/pptx/PPTXRuntimeKitExportDom.ts`，属性名、类型词汇与兜底顺序都以该文件为单一事实源。表格契约的属性名内联在 `PPTXDomConverterTable.ts` 中。三维静态帧契约的常量与类型收口在 `runtime/src/core/shared/model-static-frame-contract.ts`。

## 表格契约

**生产者**：`runtime/src/runtime-kit/public/components/data/DataTable.v1.vue`

| 属性 | 取值 | 位置 | 作用 |
| :--- | :--- | :--- | :--- |
| `data-runtime-kit-table` | `v1` | 根节点 | 标记该节点是 Runtime Kit 表格，而不是 HTML `<table>` |
| `data-runtime-kit-table-cell` | `v1` | 每个单元格 | 标记可采集单元格 |
| `data-row-index` | 0 基整数 | 每个单元格 | 行索引，决定 OOXML 中的 `<a:tr>` 归属 |
| `data-column-index` | 0 基整数 | 每个单元格 | 列索引，决定 `<a:gridCol>` 归属与顺序 |

根节点同时带 `role="table"`、`aria-rowcount`、`aria-colcount`，单元格带 `role="cell"`、`aria-rowindex`、`aria-colindex`。这些是无障碍属性，**不是**导出契约的一部分，转换器不读取它们；但因为 DataTable 用 CSS Grid 的 `div` 而非 HTML `<table>` 渲染，两者必须同时维护。

**消费者**：`runtime/src/core/services/pptx/PPTXDomConverterTable.ts`

- `isRuntimeKitTable()` 以 `data-runtime-kit-table === 'v1'` 判定根节点。
- `collectRuntimeKitCells()` 用 `[data-runtime-kit-table-cell="v1"]` 采集单元格，并读取行列索引；索引非整数或为负的单元格会被丢弃。
- `resolveCellBackgroundColor()` 向上冒泡解析单元格背景时，把 `data-runtime-kit-table="v1"` 作为**停止边界**，避免把页面背景当成单元格底色。

**改动影响**：改名或去掉任一属性，DataTable 会退化为按普通 `div` 子树导出——表格变成一堆文本框和矩形，不再是可编辑的 PowerPoint 原生表格。改坏 `data-row-index` / `data-column-index` 会让单元格错位或被丢弃。改坏背景停止边界会让整表单元格继承页面底色。

**边界**：DataTable v1 不支持合并单元格，因此这条路径不会产出 `gridSpan` / `rowSpan` / `hMerge` / `vMerge`。合并能力目前只在 HTML `<table>` 路径上由 `PPTXDomHtmlTableParser` 解析 `rowspan` / `colspan` 得到。若将来给 DataTable 增加合并，需要同时扩展单元格载荷属性和 OOXML 断言。

## 媒体契约

**生产者**：`runtime/src/runtime-kit/internal/renderers/` 下的 7 个 viewer，属性打在各自根节点上。

| 组件 | 根节点 | `data-runtime-kit-media-kind` | 报告源类型 |
| :--- | :--- | :--- | :--- |
| `MermaidViewer.vue` | `div.mermaid-viewer` | `mermaid` | `mermaid` |
| `DrawioViewer.vue` | `div.drawio-viewer` | `drawio` | `drawio` |
| `LatexViewer.vue` | `section.latex-viewer` | `formula` | `formula` |
| `EchartsViewer.vue` | `section.echarts-viewer` | `chart` | `chart` |
| `VideoViewer.vue` | `section.video-viewer` | `video` | `video` |
| `ImageViewer.vue` | `figure.image-viewer` | `image` | `image` |
| `ModelViewer.vue`（`AssetModel.v1`） | `div.model-viewer` | `model3d` | `model3d` |

`data-runtime-kit-media` 固定为 `v1`。类型词汇表 `RUNTIME_KIT_MEDIA_KINDS` 的取值与 `PptxReportSourceType` 对齐，因此可以直接作为报告源类型返回。注意组件类名与类型取值并非同名：`latex-viewer` 对应 `formula`，`echarts-viewer` 对应 `chart`；`model-viewer` 没有进入类名兜底集合，`model3d` 识别只依赖显式契约（WebGL 画布在克隆后本就是空白，兜底截图没有意义）。

**消费者**：

- `PPTXDomConverterMedia.isMediaElement()` 判断是否走媒体导出分支。
- `PPTXDomConverterMedia.resolveMediaSourceType()` 决定导出策略：`formula` 逐段导出 MathJax SVG，`chart` 优先验证下述图表数据载荷；`model3d` 优先使用静态帧覆盖图，缺失时回退局部截图；未支持的图表与 `mermaid` / `drawio` 优先找可序列化 SVG（`chart` 再退 canvas），`video` 取封面或当前帧，`image` 走图片路径或 data URL，全部失败时降级为局部截图。
- `PPTXDomConverterRaster.isTerminalMediaElement()` 判断 3D CSS 降级截图时哪些子树不该继续深入，必须与上面的媒体识别保持一致，否则会出现「媒体节点被当成普通容器整块栅格化」。

**词汇表不含 `canvas` / `svg` / `connector`**：`canvas` 和 `svg` 由标签名判定，不来自 Runtime Kit 组件；连接线走独立契约，且 `PptxReportSourceType` 中没有 `connector` 成员，硬塞进媒体词汇会让报告类型失真。

**改动影响**：去掉属性不会立刻坏——类名兜底会接住。真正的风险是**同时**改类名和属性，或者只改属性取值而词汇表没跟上：此时节点仍被识别为媒体，但 `resolveMediaSourceType` 落到标签名判定，公式会被当成普通 SVG、图表会被当成截图。新增 viewer 时必须同时补属性和 `ViewerExportDom.test.ts` 用例。

## 三维模型静态帧契约

**背景**：`ModelViewer` 的 WebGL 渲染器使用 `preserveDrawingBuffer: false`，画布像素缓冲不会被 `cloneNode` 复制，snapdom / drawImage 路径拿到的必然是空白帧。因此导出流程必须在 DOM 采集前把每个模型实例的当前帧**同步重绘并立即读回**为 PNG。

**生产者**：`runtime/src/core/services/export/model-static-frames.ts`

- `prepareModelStaticFrames(root)` 查询 `[data-runtime-kit-media-kind="model3d"]` 根节点，通过采集句柄取帧，插入 `<img data-runtime-model-frame="v1">` 覆盖层（绝对定位、100% 尺寸）并隐藏 canvas；`cleanup` 幂等移除覆盖层并恢复 canvas 可见性。
- 采集句柄由 `ModelViewer.vue` 挂载时写入根元素属性 `__runtimeModelStaticFrameHandleV1`（字符串属性名，跨 realm 有效），卸载时按同一引用注销；句柄只暴露 `describe()`（身份）与 `capture()`（同步 render + `toDataURL('image/png')`），未就绪、上下文丢失或画布退化时返回 null。
- 静态帧缓存为任务级：`OffscreenPageStage` 每任务持有 `ModelStaticFrameCache` 并在 `dispose()` 释放；键包含资源名 + 资源地址 + 视角键（场景/相机/position/target/fov/背景/光照）+ 帧像素尺寸（视口 × 收敛 DPR）。相同资源不同视角不得共用。
- 接入点：`OffscreenPageStage.preparePage`（PDF/PPTX 全部页）、`PageCaptureService.captureElement`（snapdom 前准备、finally 清理）、`createRuntimePageCaptureTarget`（clone 前准备，覆盖非项目路由 PDF 当前页）、`BrowserPrintService.appendPrintPage`（打印 clone 前准备）。已准备元素有幂等保护，内层 cleanup 不移除外层创建的覆盖层。

**消费者**：`PPTXDomConverterMedia.addModel3dStaticFrameBlock()` 只在模型根的直接子级里查找带标记的覆盖图：命中则整块导出为图片块（`sourceType: 'model3d'`、`result: 'image'`）；未命中时回退既有局部截图（`result: 'screenshot'`），截图失败按 `addSkippedItem` 语义记录。`ElementRasterizer` 局部截图路径经 `captureElement` 内部同样会准备静态帧。

**改动影响**：覆盖图标记属性丢失会让 PPTX 退化为局部截图（模型可能空白）；句柄属性名或覆盖层结构改变会同时破坏 PDF 与 PPTX 两条路径。回归由 `model-static-frames.test.ts`、`PageCaptureService.test.ts`、`OffscreenPageStage.test.ts` 与 `PPTXRuntimeKitExportDom.test.ts` 拦截。

## 图表数据契约

**生产者**：`EchartsViewer.vue` 调用 `extractNormalizedChartData()`，仅当配置满足支持范围时在根节点输出以下属性；现有媒体 v1 标记保持不变。

| 属性 | 取值 | 作用 |
| --- | --- | --- |
| `data-runtime-kit-chart` | `v1` | 声明原生图表数据版本 |
| `data-runtime-kit-chart-data` | JSON 字符串 | 提供纯数据载荷，不读取 ECharts 私有实例 |

v1 示例：

```json
{
  "version": "v1",
  "chartType": "bar",
  "categories": ["甲", "乙"],
  "series": [{ "name": "数量", "values": [10, 20], "color": "2563EB" }],
  "options": { "showLegend": true, "showTitle": false }
}
```

**消费者**：`parseRuntimeKitChartPayload()` 和 `validateRuntimeKitChartPayload()` 校验后，`PPTXDomConverterMedia` 写入 chart IR，投射器调用 PptxGenJS `addChart`。

- 支持 `bar`、`line`、`pie`、`doughnut`。柱状图为垂直类目轴；饼图和环形图仅一个系列，数值非负。
- 类目为字符串，1 至 1024 项；系列为 1 至 32 项，各系列数值必须与类目等长且为有限 number，总数值不超过 16384。JSON 属性长度最多 1 Mi 个字符。
- 类目、系列名及可选标题长度最多 2048 字符；系列颜色为六位十六进制，可带 `#`。`showLegend`、`showTitle`、`showValue` 为可选 boolean，`holeSize` 为 0 至 100 的百分比。
- 函数回调、循环对象、dataset、多轴、组合图、堆叠、平滑或面积线、渐变系列、极坐标等复杂配置返回 null。无效数据、未知版本或未知类型同样返回 null，继续原有 SVG、canvas 或截图路径，不提交坏 chart。

载荷保留系列数据与基础选项，不承诺迁移任意 ECharts 样式。PowerPoint/WPS 编辑、保存并重开尚需目标应用验收；原生路径的支持范围不能由数据 Schema 合法性单独证明。

## 连接线契约

**生产者**：`runtime/src/runtime-kit/public/components/primitives/Connector.v1.vue`，根 `<svg>` 上带 `data-runtime-kit-connector="v1"`，历史类名 `connector-svg` 保留。

**消费者**：`runtime/src/core/services/pptx/svg/ConnectorTightBounds.ts` 的 `buildConnectorSvgExportPayload()`。守卫通过后，导出不会使用整块画布容器，而是按真实连线 `path` 的几何边界（含线宽与箭头留白）计算紧边界 `viewBox` 与 PPTX 定位盒。

**改动影响**：守卫失效时连接线仍会被导出为 SVG 图片块，但定位盒退化为整个画布容器——线条在 PowerPoint 里会明显偏移或缩到极小，且不会报错。这类回归只能靠 `ConnectorTightBounds.test.ts` 拦住。

## 识别优先级

`PPTXDomConverter.visitPreparedElement()` 首先判断子树合成与裁切是否需要截图，随后**表格优先于媒体**，命中即返回。媒体识别内部顺序：

1. `data-runtime-kit-media="v1"` 且类型在词汇表内 → 用契约声明的类型。
2. 否则按历史顺序匹配类名与标签名兜底。兜底顺序是**交错**的，必须原样保留：`mermaid` → `drawio` → `formula` → `chart` → `video`（类名或 `<video>`）→ `<canvas>` → `<svg>` → `image`（类名或 `<img>`）。
3. 都不命中 → `unknown`。

兜底顺序不能改成「先判完所有类名，再判所有标签名」。例如 `<canvas class="image-viewer">` 在历史顺序下判定为 `canvas`，先判类名会误判成 `image`。`PPTXRuntimeKitExportDom.test.ts` 对这些混合节点有专门用例。

同理，连接线守卫的顺序是「契约属性 → `connector-svg` 类名」。

## Connector.v1 为什么不需要 v2

`Connector.v1.vue` 是 Runtime Kit manifest 登记的公开组件，AGENTS.md 要求「需要不兼容演进时新增 v2/v3 文件，不修改仍被依赖的旧版本文件」。给根 `<svg>` 增加一个 `data-*` 属性属于**纯增量兼容变更**，不触发该规则：

- 组件对外 API（props、事件、插槽、`import_path`）完全不变，已存在的页面源码和工作空间组件源码无需任何修改即可继续工作。
- 渲染几何、层级与样式都不变，属性不参与任何选择器或布局。
- manifest 是面向 Agent 与 Backend 的**能力目录**（`usage`、`preview_schema`、`constraints`、`audiences`），描述「怎么调用这个组件」，不是 DOM 输出登记表。
- 既有先例一致：`DataTable.v1` 早已输出 `data-runtime-kit-table="v1"`，其 manifest 条目也没有记载该属性。
- `constraints` 是写给组件使用者的约束；导出标记不是使用者需要决策的事项，写进去只会污染 Agent 上下文。
- manifest 内容 hash 是 `CodeCheckFingerprintBuilder` 的指纹输入之一，无谓改动会让代码检查缓存整体失效。

因此 DOM 导出契约记录在本文档，不进入 manifest。若将来出现**不兼容**演进（例如改变连线锚点语义、移除 props），才需要新增 `Connector.v2.vue` 并同步 manifest。

## 测试位置

| 测试 | 覆盖内容 |
| :--- | :--- |
| `PPTXRuntimeKitExportDom.test.ts` | 契约识别正反例、类型词汇与各 kind 映射、类名兜底顺序、连接线守卫、转换器分派（含 model3d 静态帧/回退） |
| `ViewerExportDom.test.ts` | 6 个 legacy viewer 真实挂载后属性存在，且能被消费端识别；移除属性后类名兜底仍生效 |
| `ModelViewer.test.ts` | 三维契约标记、采集句柄注册/注销与未就绪门禁 |
| `model-static-frames.test.ts` | 覆盖图准备/清理幂等、重复 prepare 保护、缓存分区（视角/视口/资源身份）与跨 realm 契约 |
| `Connector.v1.test.ts` | Connector 根 SVG 属性存在，且不与媒体契约混用 |
| `ConnectorTightBounds.test.ts` | 守卫负例，以及仅带属性（无类名）时的紧边界导出结果 |
| `PPTXDomConverterTable.integration.test.ts` | HTML 表格与 DataTable 两条路径的真实 OOXML 输出 |
| `DataTable.test.ts` | DataTable 渲染结构与表格契约标记 |
| `S4NativeEditingSemantics.test.ts` | 简单图表数据提取、原生 chart IR、列表与组合 |
| `ExportReviewRegression.test.ts` | 跨窗口节点、坏图表载荷安全降级、列表实际段落、连续图元组合与原子页容错 |

生产者与消费者的属性名对拍由 `ViewerExportDom.test.ts` 与 `Connector.v1.test.ts` 承担：它们从 `PPTXRuntimeKitExportDom` 导入常量再断言组件输出，任一侧单独改动都会失败。

修改契约后运行：

```powershell
pnpm run test:runtime:gate
```

## 相关文档

- [Connector 连接线组件](../components/connector.md)：连线组件的属性、示例与使用约束。
- [Runtime Kit 能力说明](../runtime-kit-capabilities.md)：公开能力目录、`.vN` 版本规则与 manifest 边界。
- [AGENTS.md](../../../../AGENTS.md)：Runtime Kit 约束与测试要求。
