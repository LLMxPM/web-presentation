# 三维资源复用与 Three.js 渲染接入分析

分析日期：2026-10-16。状态：设计分析，尚未实施。

详细工作包、契约、依赖、验收门槛与修订后的工作量见[三维资源复用与渲染实施计划](./threejs-resource-implementation-plan.md)，后续排期以实施计划为准。

## 与文件存储鉴权链路的对齐

本分析按 2026-10-16 的受保护文件交付链路规划。详细平台目标与迁移状态见[文件存储鉴权与缓存规划](./file-storage-auth-cache-plan.md)。三维资源沿用现有文件身份和授权入口，不新增匿名素材通道，也不把 Three.js Loader 直接接到对象存储。

| 读取场景 | 身份与入口 | 三维接入约束 |
| :--- | :--- | :--- |
| Editor 资源库下载、直接读取 | 当前用户会话访问 `/api/workspaces/{workspace_id}/assets/{asset_id}/file?hash={hash}` | Backend 检查工作空间权限和当前文件版本；历史版本与当前版本解析同一根资源，URL 不能当作公开链接 |
| Runtime 预览与 Renderer 浏览器 | 短期预览票据 P 访问 `/preview/artifacts/{artifact_id}/assets/{file_hash}?token=P` | P 绑定 artifact；文件必须属于该 artifact 的 manifest。Runtime 只在 `asset_base_url_auth=preview_token` 时附加 P；续签由 Editor 会话重新检查权限，不能由旧 P 自行续期 |
| Runtime / 构建 Worker 内部回源 | 服务票据 S 或构建任务授权访问 `/internal/runtime/preview-artifacts/{artifact_id}/assets/{file_hash}` | Backend 校验 artifact 与 manifest 成员；S 不进入用户 HTML、页面源码、构建产物或外部地址 |
| 独立构建运行 | Build Worker 将已授权素材物化进构建工作区 | 产物只包含本地文件和 Three.js 运行时代码，不依赖预览票据、服务凭证或在线 Backend |

旧 `public_assets.py` 源文件仍保留，但它没有挂入当前 Backend API Router；Gateway 也阻断 `/public`。因此不能沿用 `/public/assets` 作为 GLB 或纹理读取路径，也不能以此处的旧实现推导当前访问语义。鉴权必须先于缓存、条件响应和文件读取；缓存命中、304、HEAD、Range 均不得补足或绕过授权。

M1 的 GLB 必须以固定文件 hash 进入预览 artifact manifest，自包含性校验拒绝任何外部依赖。当前页面创建预览时绑定当时解析到的文件 hash；历史页面按保存的引用集合解析当前资源；截图任务和构建 Release 在创建时解析并持有当时的文件（替换即全局更新，不冻结历史视图）。M2 多文件 glTF 的相对 URI 只能解析到已校验并纳入同一 revision 与 manifest 的成员，不能拼接任意 Backend、对象存储或外部 URL。无法静态确定的动态资源名可以保存，但不进入精确引用集合，构建侧按项目额外资源规则收集，不能声称引用闭合完整。

## 平台定位与接入方向

平台提供通用三维资源的托管、管理、引用与渲染能力，让同一份资源在多个项目、页面和组件中复用。Three.js 是 Runtime 内部的渲染实现；资源按标准格式保存，页面通过稳定资源名引用，并分别配置展示参数。

建议以 glTF 2.0／GLB 为主要资源格式，先完成自包含 GLB 的上传、预览、重复引用、替换更新、历史保护、截图导出和独立构建，再扩展 glTF 多文件资源包。平台维护格式支持范围和展示参数契约，原始资源继续使用标准格式。

与 Draw.io 的对应关系是：Draw.io XML 交给图表渲染器，glTF／GLB 交给三维渲染器。应优先复用资源体系和标准文件生态，不增加作为前置条件的自定义场景 DSL、`.three.json` 或基础几何体编辑协议。对象树编辑、建模和时间轴可由外部工具完成；需要代码驱动的特殊交互、程序化效果，复用现有工作空间组件体系。

首期应验证的产品目标是：一份产品模型上传一次，页面 A 展示正面、页面 B 展示侧面、页面 C 放大局部，三个实例引用同一资源；替换资源后当前与历史预览统一显示新文件，在途任务使用任务开始时的文件，已发布产物独立于当前资源保持可用。

## 资源 渲染器与引用实例

| 层次 | 保存什么 | 复用边界 |
| :--- | :--- | :--- |
| 资源本体 | 标准模型或场景文件，以及文件内的节点、材质、纹理、相机和动画 | 工作空间内统一管理，多项目、页面和组件引用；可下载到外部工具继续使用 |
| 渲染能力 | 格式加载、相机适配、查看交互、动画播放、首帧状态与静态帧输出 | Runtime 提供版本化公共组件，内部使用 Three.js |
| 引用实例 | 所在页面的尺寸、视角、背景、交互与播放设置 | 保存到页面或组件的引用参数，不修改或复制原文件 |
| 派生产物 | 缩略图、静态导出帧、模型分析摘要 | 关联源版本和展示参数，可失效重建，不替代原始资源 |

glTF 可以承载完整场景，不限于单个 mesh，因此首期无需把“模型”和“场景”强制拆成两种资源。不同视角用实例参数表达；需要一组可复用的展示参数或组合多个资源时，可以用现有工作空间组件封装。不同工作空间之间的复用通过现有包导入导出与权限模型推进。

资源复用也包含运行时约束：同一文件可以缓存下载和解析结果，但相机、节点变换和动画播放状态必须按实例隔离。一个实例卸载不能释放另一个实例仍在使用的材质、纹理和几何体；带骨骼的模型还需要正确的实例克隆策略。

## 通用格式选择与支持范围

### 主格式采用 glTF 2.0 和 GLB

glTF 定义场景节点、网格、材质、纹理、相机和动画等结构；GLB 是其二进制容器形式。两者属于同一格式体系，适合作为外部工具与平台之间的交付格式。能力边界以 [Khronos glTF 2.0 规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) 为依据。

| 格式 | 接入定位 | 支持策略 |
| :--- | :--- | :--- |
| 自包含 GLB | 首期正式入口，单文件便于上传、快照、分发和打包 | 验证容器、glTF 版本、必需扩展、数据规模及依赖自包含性 |
| glTF 与关联 bin、纹理 | 后续标准多文件入口 | 一次导入完整文件集，保留相对路径并绑定完整版本 |
| Three.js Object/Scene JSON | 引擎专用序列化格式 | 按实际兼容需求增加转换或渲染适配，不作为通用主格式 |
| OBJ、STL 等其他模型格式 | 后续按使用需求评估 | 明确格式损失和渲染能力后再增加 loader 或可选转换 |
| JavaScript、Vue 与自定义 Shader | 组件源码与程序化效果 | 由现有组件开发、校验和发布流程承载 |

保留用户上传的原始字节、文件名与格式信息；下载和导出继续得到标准文件。若提供格式转换或模型优化，应明确产生新的派生文件并记录来源，避免静默改写原资源。

### 分阶段声明格式能力

首期建议支持自包含、无额外压缩解码器依赖的 glTF 2.0 GLB、内嵌 PNG/JPEG 纹理和明确列出的核心材质能力。资源内已有的相机、动画等信息应保留并提供摘要；首期可以只展示固定姿态，动画播放单独列为后续能力，不能因首期不播放而丢弃原始动画数据。

GLB 仍可能引用外部文件，不能仅凭扩展名判定自包含。上传时检查 buffers、images 及允许扩展中的 URI，首期拒绝未随文件提供的外部依赖。后续 glTF 多文件导入应验证所有依赖已随包提交。依据见 [GLB 文件规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#glb-file-format-specification)。

Draco、KTX2、Meshopt 等能力需要额外解码集成。应发布明确的扩展支持矩阵，对不支持的必需扩展报错；可选扩展只有在规范允许并接受相应降级时才能忽略，同时给出提示。启用解码能力时，把实际需要的 Worker、WASM、解码脚本及版本一起纳入发布和独立构建。相关接口见 [GLTFLoader 文档](https://threejs.org/docs/pages/GLTFLoader)。

## 现有 Draw.io 链路与复用范围

| 环节 | 当前实现及证据 | 三维资源接入改动 |
| :--- | :--- | :--- |
| 类型与存储 | [AssetType](../../../backend/app/models/enums.py)、[WorkspaceAsset](../../../backend/app/models/asset.py)；工作空间内 name 唯一，保存文件 hash、归档和历史信息 | 新增按内容定义的三维类型，继续使用现有资源身份 |
| 上传与替换 | [AssetService](../../../backend/app/services/asset_service.py) 提供上传、替换、覆盖历史及引用保护；Draw.io 额外支持文本读写 | GLB 使用二进制上传与替换；不接入面向文本的 512 KiB 内容编辑流程 |
| HTTP 契约 | [内部资源路由](../../../backend/app/api/routes/assets.py)、[External 资源路由](../../../backend/app/api/routes/external/assets.py)、[DTO](../../../backend/app/schemas/asset.py) | 扩展枚举、格式校验、元数据和外部文件替换契约 |
| Editor 管理 | [资源库](../../../editor/src/views/AssetsView.vue)、[资源详情逻辑](../../../editor/src/views/assets/useAssetDetail.ts)、[类型配置](../../../editor/src/components/project/asset-manager.ts) | 增加上传、详情、替换、历史、引用入口与三维筛选 |
| 资源预览 | [AssetPreviewService](../../../backend/app/services/asset_preview_service.py) 创建 `asset_host` 和短期 P；[AssetPreviewFrame](../../../editor/src/components/project/AssetPreviewFrame.vue) 打开隔离 Runtime iframe | 复用 artifact-scoped 受保护素材入口；三维文件必须命中 manifest，不能走匿名 URL |
| 页面引用 | [AssetDrawio.v1.vue](../../../runtime/src/runtime-kit/public/components/assets/AssetDrawio.v1.vue) 按资源名解析并渲染 | 新增 `AssetModel.v1.vue`，按资源名加载标准文件，接受实例展示参数 |
| 实际渲染 | [DrawioViewer](../../../runtime/src/runtime-kit/internal/renderers/DrawioViewer.vue) 加载 XML 和 GraphViewer 后输出 SVG | 新增 Runtime 内部模型 Viewer，按需加载本地打包的 Three.js 与 loader |
| 首帧等待 | [visual-assets](../../../runtime/src/core/utils/visual-assets.ts) 识别 Draw.io 状态，聚合到 [render-ready.v1](../../../runtime/src/core/utils/render-ready.ts) | 增加模型与纹理解码、实例设置和首帧完成的探针 |
| 引用与构建 | [ResourceReferenceParser](../../../backend/app/services/resource_reference_parser.py)、[ProjectArtifactBuilder](../../../backend/app/services/project_artifact_builder.py) 收集引用与构建资源 | 补测 AssetModel 静态引用；多文件阶段展开标准文件依赖 |
| 资源回源 | [工作空间文件入口](../../../backend/app/api/routes/assets.py)、[预览素材入口](../../../backend/app/api/routes/preview.py)、[Runtime 内部入口](../../../backend/app/api/routes/internal_runtime.py) 共用受保护文件响应与授权校验 | GLB 和纹理按用户会话、P 或 S 的用途读取；逐条验证 manifest 归属、MIME、CORS、hash 与缓存前鉴权，不回退 `/public/assets` |
| 导出 | [PPTX 媒体转换](../../../runtime/src/core/services/pptx/PPTXDomConverterMedia.ts) 有 SVG 与 canvas 路径 | 补齐确定的三维静态帧采集，供 PNG、PDF 和 PPTX 使用 |

当前 [runtime/package.json](../../../runtime/package.json) 未声明 `three`，资源枚举和 Runtime Kit 清单也没有三维公共组件。现有 `analysis_metadata` DTO 主要描述图标分析，三维分析摘要需要同步定义新的类型结构。

## 资源身份 版本与依赖管理

### 标准资源身份

拟议新增 `asset_type=model3d`，`asset_role=content`。名称描述资源内容，与内部使用 Three.js、其他引擎或不同 loader 解耦。当前 `render_type` 从 `asset_type` 直接派生，首期可以同样使用 `model3d`，并在 Runtime 宿主页增加对应分支。

GLB 使用 `model/gltf-binary`，`content_editable=false`；文件内含 JSON 不代表应向用户提供通用文本编辑入口。后续多文件 glTF 同样优先采用完整资源集替换，避免一次只改入口 JSON 导致依赖与版本不一致。

复用现有 name、file hash、复制、归档、恢复和历史副本机制。已有字符串类型列通常无需因新增枚举值而改列；成员表、版本摘要和派生物索引的增量则需要单独迁移。资源比例仅表达人工设置的展示建议，三维包围盒不应被当作固定二维宽高比。

### 多页面引用与更新语义

- 当前编辑中的页面按 name 解析当前有效资源；替换文件保留资源身份和 name，并生成历史副本。
- 当前引用各自保留相机、背景和交互参数；原资源更新后重新渲染，并使对应检查、缩略图与截图缓存失效。
- 页面保存历史需要保存当时的引用集合（组件递归与资源名），保证历史版本可重建结构；资源替换后历史预览同步显示新文件（替换即全局更新），不承诺还原旧模型。
- 预览 artifact 和发布构建在创建时固定解析到的资源 hash；在途引用由短期持有保护，避免只有 hash 而文件已被清理。
- 替换后如已选相机或动画不再存在，展示可诊断的提示；显式选择失效应进入校验失败，默认自动取景则可以重新计算。

资源库默认预览视角与页面实例视角分别管理。资源详情中的临时旋转只影响本次查看；“设为默认预览”与“保存到页面”应是明确操作。首期可以用统一自动取景生成资源默认缩略图，页面视角直接保存在组件属性中。

### glTF 多文件依赖

单文件自包含 GLB 先作为一个资源与一个文件管理，无需为其内部每张纹理建立独立资源记录。多文件阶段建议把入口 glTF 和关联文件作为一个逻辑资源集提交，保留标准目录结构：

```text
product/
  scene.gltf
  geometry.bin
  textures/
    base-color.png
    normal.png
```

平台需要保存入口路径、成员规范化路径、成员 hash、大小、MIME 及整套资源的版本摘要；成员文件可按内容去重，但逻辑上作为完整资源集原子更新。包和 manifest 用于运输、索引与版本绑定，下载时仍提供原始 glTF、bin 和图片。首期无需把内部成员提升为用户资源库中的独立图片。

当前单资源 name→hash 映射不足以表达上述文件集，需要同步扩展存储、manifest 与构建物化。Runtime loader 通过受控的相对路径映射寻找成员，不直接拼接后端 hash URL 推测文件目录。导入时拒绝路径穿越、绝对路径、重复成员、大小写歧义、缺失依赖与超出预算的包。

同一资源集的依赖不允许落到其他工作空间或任意网络地址。若后续支持引用资源库已有贴图，应再增加资源之间的依赖索引、改名与删除保护、文件持有保护和包导入重绑定；不把这套能力作为首期单文件渲染的前置条件。

## 页面与组件的渲染入口

建议公开 `AssetModel.v1`，拟议路径为 `@runtime-kit/public/components/assets/AssetModel.v1.vue`。组件按 name 获取标准资源，并提供有限的实例展示参数。以下仅展示拟议用法，正式实施时需定义 props、默认值和字段约束：

```vue
<script setup lang="ts">
// 按资源名引用同一模型，各实例分别设置视角。
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
</script>

<template>
  <AssetModel
    name="product"
    :camera-position="[0, 1, 4]"
    :camera-target="[0, 0, 0]"
    class="w-full h-80"
  />
  <AssetModel
    name="product"
    :camera-position="[4, 1, 0]"
    :camera-target="[0, 0, 0]"
    class="w-full h-80"
  />
</template>
```

展示参数分为尺寸、相机、背景、交互和播放设置。它们可以有共享 Schema 进行校验，但该 Schema 只描述如何查看标准资源，不定义物体、材质或场景内容。页面不需要复制模型文件，也不需要嵌入大型 glTF JSON 或 base64。

建议明确以下优先级：显式实例参数优先；未指定时使用可用的资源相机；资源没有相机时才自动取景。源文件中可支持的材质、节点和相机保持原语义；资源缺少可用光照时可以使用声明过的查看器默认光照。自动取景依据实际 bounds 计算，处理空场景、极端尺寸、长宽比与裁剪面，不随意归一化原文件的几何尺寸。

相机显式参数的坐标系和单位与加载后的资源一致；输入必须为有限数值，position 与 target 不能重合。首期页面编辑态默认关闭查看交互，演示态可按实例启用。后续动画选段、时间、循环等参数同样属于实例状态。

发布组件时同步 [Runtime Kit manifest](../../../runtime/src/runtime-kit/manifest/runtime-kit.manifest.json) 的 props、示例、约束和 previewSchema。静态引用解析、组件封装、参数中的动态资源名及构建额外资源规则需联动验证。

## 各模块需要完成的工作

### Backend 资源服务与接口

复用现有上传、文件替换、复制、历史、归档与预览服务，在资源边界增加格式校验和类型化摘要。上传校验应覆盖 GLB magic、容器版本、chunk 长度、glTF 版本、必需扩展、引用范围与资源预算；完整的格式合规检查与实际可渲染性分别验证，不能以文件头正确代替后续检查。

Backend 提取可静态读取的相机、动画、节点和文件规模摘要；需实际加载才能确认的 bounds、解码规模或视觉结果由 Renderer 计算。大型 GLB 不经文本接口读写，上传及校验要考虑内存、时限和解码后预算，不在同步事务里启动浏览器。

| 用途 | 现有内部 API | 接入变化 |
| :--- | :--- | :--- |
| 上传 | `POST /api/workspaces/{workspace_id}/assets/upload` | 接受 model3d 和经过格式校验的 GLB |
| 替换 | `POST /api/workspaces/{workspace_id}/assets/{asset_id}/replace` | 保留资源身份，写入历史，更新摘要并使缓存失效 |
| 详情与引用 | 复用现有资源列表、详情响应和 references 入口 | 返回格式能力、分析摘要与使用位置 |
| 单资源预览 | `POST /api/workspaces/{workspace_id}/assets/{asset_id}/preview-artifact` | 为标准三维资源生成现有 asset_host artifact |
| 内容 diff | 现有 `content/preview` 为文本差异接口 | 保持文本职责，GLB 通过版本信息与视觉预览比较 |

External API 已有 `/api/v1/assets` 上传和文本 `/content` 路径，但当前 External 资源路由没有单独的按 ID 替换二进制文件入口。应明确评估复用已有 overwrite 语义，或补齐按 ID 替换契约；如新增，需定义 scope、工作空间权限、幂等键、版本基线、失败回滚和响应，不能把文本更新接口描述成已有模型替换能力。

错误码建议按资源或格式命名，例如 `MODEL3D_FORMAT_INVALID`、`MODEL3D_EXTENSION_UNSUPPORTED`、`MODEL3D_DEPENDENCY_MISSING`、`MODEL3D_EXTERNAL_URI_FORBIDDEN` 和 `MODEL3D_LIMIT_EXCEEDED`。非法输入返回 400，访问沿用现有 403/404 规则，资源版本基线冲突返回 409；错误返回有界的文件或字段位置。

### Editor 资源管理

增加三维资源筛选、上传格式说明、资源详情、替换与历史入口、资源选择和 Runtime 预览。详情展示模型摘要与格式支持提示，默认不提供 JSON 文本编辑器、几何体创建或场景对象树。具体 UI 继续遵循 [DESIGN.md](../../../DESIGN.md)。

页面或组件引用侧提供视角和交互设置，复用现有可视化编辑、属性面板与组件 previewSchema 的边界。设置变化只更新当前实例，不替换资源。项目资源面板、AssetPicker、建议参考资源、构建额外资源和包导出弹窗同步新类型。

资源列表使用静态缩略图或类型图标，详情预览才激活 WebGL。缩略图绑定资源版本、默认预览设置和渲染配置；页面导出帧另绑定实例参数，二者不能仅以 asset ID 共用缓存。

### Runtime 渲染实现

`AssetModel.v1.vue` 负责资源名、实例参数和兜底；内部 ModelViewer 与模块化 loader、相机适配、实例管理、资源释放和静态帧采集负责实际渲染。通过根 pnpm workspace 增加 `three` 生产依赖，并在所选版本需要时补齐类型依赖。

首期采用 WebGLRenderer，按需加载 Three.js、GLTFLoader 与必要 addon，避免所有页面预览都加载三维引擎。当前 WebGLRenderer 使用 WebGL 2，部署需验证该能力，见 [WebGLRenderer 文档](https://threejs.org/docs/pages/WebGLRenderer)。

生命周期重点包括 ResizeObserver 与 DPR 上限、按需重绘、隐藏或离屏时暂停、快速切换的异步结果失效、零尺寸恢复、context lost 和加载错误。同一资源多个实例的缓存与引用计数需明确，卸载时清理所属循环、控制器、Observer、Blob URL 和 GPU 对象。Three.js 资源需要显式释放，见 [对象释放文档](https://threejs.org/manual/pages/how-to-dispose-of-objects.html)。

多文件阶段使用独立 LoadingManager 跟踪加载并映射受控成员路径；URL 重写机制见 [LoadingManager 文档](https://threejs.org/docs/pages/LoadingManager.html)。该映射仅解析已通过 Backend 校验并属于当前 artifact 的文件集，不能替代服务端的依赖和权限检查。

## 预览 截图与发布输出

### 首帧与静态帧

增加如 `data-runtime-model-state="loading|ready|error"` 的状态，由 visual-assets 汇总到现有 render-ready.v1。ready 应表示资源和纹理解码完成、实例设置生效、有效尺寸下的目标帧已经绘制。Renderer 继续核对 artifactId 与 inputDigest，沿用 [render_ready.py](../../../renderer/wp_renderer/engine/render_ready.py) 的协议等待。

场景动画和自动旋转由 JavaScript 驱动，现有 [executor](../../../renderer/wp_renderer/engine/executor.py) 的 `screenshot(animations="disabled")` 无法自动冻结它们。截图使用保存的实例相机和明确的时间点；首期固定姿态，后续按选定动画片段与时间采样，避免把用户临时拖动或墙上时间写入结果身份。

### 输出契约

| 输出 | 应实现的行为 | 关键要求 |
| :--- | :--- | :--- |
| 原始资源下载与包导出 | 保留 GLB 或完整 glTF 文件集 | 外部工具可继续使用，不导出成平台专用场景格式 |
| Renderer PNG | 完整加载资源，等待目标帧后浏览器截图 | 模型与纹理可见，失败明确，不以占位图冒充成功 |
| PDF 与 PPTX | 将实例对应的三维静态帧作为图片放入现有导出链路 | 位置、背景、透明度与清晰度正确；首期为静态图片 |
| 独立网页构建 | 打包引擎、标准文件、成员与必要解码器 | 断开 Backend 和外部 CDN 后仍能展示，实例配置保留 |

当前 [PPTXDomConverterMedia](../../../runtime/src/core/services/pptx/PPTXDomConverterMedia.ts) 的普通 canvas 路径直接读取像素；[PageCaptureService](../../../runtime/src/core/services/PageCaptureService.ts) 与 [PDFExportService](../../../runtime/src/core/services/PDFExportService.ts) 使用页面采集。三者都需要明确的三维静态帧准备流程。

建议冻结相机与时间，在重新绘制后立即生成 PNG，或从专用 render target 读回；DOM 采集期间使用该图像，结束后恢复。WebGL drawing buffer 可能在绘制后被清空，不能仅依赖任意时机的 toDataURL。相关行为见 [Three.js 截图说明](https://threejs.org/manual/pages/tips.html#taking-a-screenshot-of-the-canvas)。

为三维媒体增加按内容命名的 `data-runtime-kit-media-kind=model3d`，联动媒体类型词汇、PPTX 转换分支和报告，并更新 [媒体 DOM 契约](../runtime/integration/pptx-export-dom-contract.md)。静态帧身份包含资源版本、依赖摘要、实例相机、背景、动画时间、视口、DPR 与渲染配置版本。

持久化缩略图通过现有 render_requests 派发到独立 Renderer。当前远程协议只有 page.capture、page.diagnose 和 component.diagnose；可构造内部页面包装资源以复用 page.capture，或明确扩展资源捕获契约。资源预览 artifact 不能被视为已经支持独立资源截图任务。

### 文件回源与构建物化

验证 GLB、glTF、bin 与纹理响应的 MIME、CORS、重定向、缓存和版本绑定。多文件 glTF 入口采用 `model/gltf+json`，成员按实际类型响应；loader 使用受控资源地址，不能仅因普通图片可显示就认定 WebGL 纹理加载可用。

首期构建物化自包含 GLB；多文件阶段增加完整成员收集和相对路径映射。资源包、组件包、样式包和项目模板包统一使用同一次导出收集的文件集，跨工作空间导入时重绑定资源身份；内部 glTF 相对路径应保持可解析，依赖不能从包外临时获取。

真实 Renderer 镜像需要验证 WebGL 2、软件渲染、shader 编译和非空截图，并记录引擎、Chromium 与渲染后端身份。继续沿用单槽、租约、期限、取消和 attempt 围栏；在固定执行环境设定视觉容差基线，混版 Runtime 按能力和构建版本选择实例。

## AI 与外部 Agent 的职责

AI 优先搜索和选择已有三维资源，再把资源名及实例展示参数写入页面或组件。工具返回格式、相机、动画与支持范围摘要；GLB 不作为文本内容注入模型，也不通过 EditableAssetType 开放文本改写。需要新素材时走文件上传或已有资源导入能力，程序化生成效果走组件源码流程。

确需调整工具参数或说明时，由 [tool_specs.py](../../../backend/app/ai/tool_specs.py) 派生披露、目录和 Editor 展示；沿用现有内容助手。未来如增加模型转换或必须等待浏览器的重任务，应接入统一 ExternalBatch/ExternalTask 与写围栏，不在普通工具调用中长期执行。

HTTP DTO 改动后执行 codegen:editor-api 和 test:contracts:generated；独立 CLI、MCP 同步资源枚举、上传、替换、查询、引用与能力说明。新增三维资源不等于两个消费者已完成适配。External API 变更执行真实 Nginx 契约回归，发布后从 Gateway 验证，遵循 [External Agent API v1](../reference/external-agent-api.md)。

## 实施阶段与工作量

| 阶段 | 主要工作 | 完成标准 |
| :--- | :--- | :--- |
| P0 格式与渲染验证 | 标准 GLB 样本、Runtime Viewer、首帧、真实 Renderer 镜像、静态导出与构建验证 | 明确支持矩阵，PNG、PDF、PPTX 和独立网页均有实际产物 |
| P1 单文件资源复用 | model3d、上传替换、AssetModel、实例视角、Editor、引用索引、在途持有与缓存、外部契约 | 一份 GLB 多页面多视角复用，替换与在途任务行为正确 |
| P2 多文件与格式扩展 | glTF 文件集、成员存储、依赖校验、原子版本、包导入导出与构建；按需增加解码器和动画播放 | 标准资源及依赖可完整迁移和交付，支持矩阵对应实际能力 |

上表为分析阶段的初步拆分。详细计划计入资源在途持有与替换语义、并发替换、独立 CLI/MCP 和镜像验收后，M0+M1 修订为 22–34 人日，多文件 M2 追加 8–12 人日；该估算假设复用现有受保护文件链路，不另建授权系统，后续排期以[实施计划](./threejs-resource-implementation-plan.md)为准。三维建模器、场景 DSL 和对象树编辑器不纳入上述范围，后续有明确产品需求时单独评估。

| 模块 | 重点入口 | 主要增量 |
| :--- | :--- | :--- |
| Backend 资源 | enums、asset DTO、AssetService，新增格式校验与摘要模块 | 标准文件支持、替换历史、预算与支持矩阵 |
| Backend 预览与构建 | AssetPreviewService、manifest 元数据、ProjectArtifactBuilder、检查与截图缓存、包服务 | 资源身份与在途持有、依赖物化、反向引用与缓存身份 |
| Runtime | Runtime Kit、AssetPreviewView、visual-assets、页面采集与 PPTX 转换 | 标准资源 Viewer、实例参数、生命周期和静态帧 |
| Editor | 资源列表与详情、AssetPicker、页面属性和项目资源面板 | 上传与复用流程、实例展示配置、历史与预览 |
| Renderer | render_ready、executor 和交付镜像测试 | 首帧、固定姿态、WebGL 与资源释放验证 |
| AI 与外部契约 | 工具规格、OpenAPI、独立 CLI/MCP 消费者 | 查找复用、文件操作与引用参数支持 |

## 验收与发布要求

### 以复用闭环作为验收主线

| 范围 | 必须验证的结果 |
| :--- | :--- |
| 标准格式 | 合法 GLB 有真实输出，下载文件保留原始字节；glTF 多文件导出后仍能被独立工具消费 |
| 多实例复用 | 同一资源在多个页面、组件及同一页面的不同实例展示不同视角，实例状态与卸载互不干扰 |
| 更新与历史 | 文件替换保留 name 和身份；当前缓存失效，页面历史同步显示新文件，资源归档历史与已发布构建不漂移 |
| 边界校验 | 错误容器、越界数据、未知必需扩展、外部 URI、路径穿越、缺失依赖与超预算均有明确结果 |
| 工作空间隔离 | 无权资源和跨空间成员不能加载；跨工作空间包导入可正确建立新的资源身份 |
| 运行生命周期 | Resize、快速切换、异步晚到、context lost、连续挂载卸载；循环与 GPU 资源不持续累积 |
| 截图与导出 | 必需资源未完成不能 ready；实际检查 PNG、PDF、PPTX，无空白、缺纹理或实例视角混淆 |
| 构建与分发 | 关闭 Backend 和外部网络后发布网页可展示；文件集、材质、必要解码依赖完整 |
| 容器与任务 | lite 和分服务镜像真实截图通过；超时、取消和重试后进程、临时产物及槽位正确释放 |

普通 DOM 布局检查只能识别 canvas 外部矩形，不能判定模型被相机裁剪、光照过暗或材质错误。视觉验收应结合加载诊断和实际截图，跨 GPU 环境使用固定基线与容差，不承诺任意环境像素完全一致。

### 实现时的测试入口

按修改范围执行资源上传替换、权限、历史、引用、包与快照测试，以及 Runtime Viewer、visual-assets、manifest、导出和构建测试。完整集成阶段执行：

```powershell
pnpm run codegen:editor-api
pnpm run test:contracts:generated
pnpm run test:backend:unit
pnpm run test:backend:api
pnpm run test:backend:integration
pnpm run test:runtime:gate
pnpm run test:editor:gate
pnpm run test:renderer
pnpm run test:contracts
pnpm run test:contracts:gateway
pnpm run test:render-e2e
pnpm run test:repository
```

远程协议变化时同步 Python DTO 与 JSON Schema，并运行 test:render-contracts；新增成员或派生物表时补充双库迁移与事务验证。现有 render-e2e 要增加多实例三维资源和像素产物断言，不能用现有普通页面截图通过代替。

发布时更新 Runtime 构建身份，校验新公共组件与新资源类型的兼容性；渲染指纹覆盖引擎、规则、依赖与实例展示参数。实现完成后更新资源管理、Runtime Kit、页面引用、媒体 DOM、外部契约和部署验收文档；正式增加产品能力时同步顶层 README。
