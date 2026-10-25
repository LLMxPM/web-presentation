# Backend 对接 API

本文档面向 Backend/平台团队，定义 Runtime 依赖的公开预览入口和内部 preview artifact 接口。

## 1. 总体原则

- Preview 为**无状态、短生命周期**链路，不保存可恢复的 preview session。
- Backend 负责创建临时 `PreviewArtifact`，并签发自包含的 `PreviewContextToken`。
- Runtime 只认两类输入：
  - `x-runtime-preview-context: <PreviewContextToken>`
  - `/internal/runtime/preview-artifacts/{artifact_id}/...`

## 2. 公开预览入口

该入口由 Backend 提供给浏览器访问，Runtime 不直接对外暴露。

### 推荐入口

`GET /preview/artifacts/{artifact_id}?token=<PreviewContextToken>`

#### 处理职责

- 校验用户登录态
- 校验租户/项目/工作空间权限
- 校验 token 与 `artifact_id` 一致
- 反向代理到 Runtime：`GET /__preview`

#### 代理到 Runtime 时必须附带的请求头

```http
x-runtime-preview-context: <PreviewContextToken>
```

## 3. Runtime 内部 API

以下接口由 Backend 提供给 Runtime 调用，默认都要求服务级鉴权。

### 公共请求头

```http
Authorization: Bearer <RuntimeServiceAccessToken>
x-runtime-preview-context: <PreviewContextToken>
Accept: application/json
```

## 4. 获取 Preview Artifact Manifest

### `GET /internal/runtime/preview-artifacts/{artifact_id}/manifest`

#### 成功响应示例

```json
{
  "artifact_id": "rel_20260411_001",
  "tenant_id": "tenant_a",
  "preview_kind": "page",
  "owner_scope": {
    "scope_type": "project",
    "project_id": "proj_demo",
    "workspace_id": "ws_demo"
  },
  "entry_descriptor": {
    "entry_type": "module",
    "module_path": "src/views/project/HomePage.vue"
  },
  "version": "preview-artifact",
  "modules": {
    "src/workspace-components/CMP_DEMO/v/1.vue": {
      "path": "src/workspace-components/CMP_DEMO/v/1.vue",
      "hash": "sha256:abc123"
    }
  },
  "assets": {
    "img/logo/ppt-e.png": "assets/logo/ppt-e.abc123.png"
  }
}
```

#### 关键约束

- `artifact_id` 必须与 token 中的 `artifact_id` 一致
- `preview_kind / owner_scope / entry_descriptor` 必须与 token 中声明一致
- 单页面预览入口模块允许不进入 `modules` 白名单，但仍必须能通过 `modules?path=` 拉到源码

## 5. 获取标准化配置包

### `GET /internal/runtime/preview-artifacts/{artifact_id}/config-bundle`

#### 说明

- 返回 Runtime 启动所需的 JSON 配置包
- 项目/页面预览必须包含 `app/routes/icons/themes/fonts/module_resolver`
- `module_resolver` 中必须下发 `remote_component_prefix`、`runtime_kit_alias`、`runtime_kit_manifest_version`、`runtime_kit_exports`
- 组件预览额外包含 `component_preview`
- 组件预览页面尺寸由 `app.app.page.width/height` 唯一决定，同时也是 iframe 尺寸和截图视口尺寸
- 页面内容基础字号与默认图标描边宽度由 `app.app.page.baseFontSize/iconDefaultStrokeWidth` 决定，组件预览可通过 `preview_options.page` 覆盖；`baseFontSize` 替代 Tailwind 默认 16px 基准，语义字号和间距按 `baseFontSize / 16px` 倍率渲染；Runtime shell UI 不跟随页面基础字号，页面内图标尺寸默认跟随页面基础字号，局部使用 Tailwind 尺寸类控制

#### 组件预览片段示例

```json
{
  "component_preview": {
    "component_import_path": "@workspace-components/CMP_DEMO/v/1",
    "component_source": "workspace_component",
    "component_code": "CMP_DEMO",
    "component_version_no": 1,
    "display_name": "示例组件",
    "schema": {
      "props": {
        "title": {
          "type": "string",
          "default": "Hello Preview"
        }
      }
    },
    "placement": {
      "width_mode": "percent",
      "width_value": 100,
      "height_mode": "auto",
      "height_value": null,
      "horizontal_align": "center",
      "vertical_align": "center",
      "padding": 48
    }
  }
}
```

Runtime Kit 内建组件预览使用同一个 `component_host`，但目标组件由 Runtime 本地 `@runtime-kit/...` 模块加载：

```json
{
  "component_preview": {
    "component_import_path": "@runtime-kit/public/components/primitives/Icon.v1.vue",
    "component_source": "runtime_kit",
    "component_code": "Icon.v1",
    "runtime_kit_component_name": "Icon.v1",
    "runtime_kit_manifest_version": "1.0.0",
    "display_name": "图标渲染器",
    "schema": {
      "props": {
        "name": {
          "type": "string",
          "default": "home"
        }
      }
    },
    "placement": {
      "width_mode": "fixed",
      "width_value": 320,
      "height_mode": "auto",
      "height_value": null,
      "horizontal_align": "center",
      "vertical_align": "center",
      "padding": 80
    }
  }
}
```

Runtime Kit 组件预览 artifact 的 `manifest.modules` 必须为空对象；Runtime 只允许通过 Runtime Kit manifest 中公开的本地模块路径加载组件和 schema slot 引用。

依赖 Vue Router 或 Runtime 配置的页码、目录和导航能力不再以 UI 组件形式进入核心公开能力目录。Backend/Agent 应使用 `useCurrentPage`、`useRouteCatalog`、`usePageNavigation` 获取数据或控制能力，并在页面源码中自行生成页码、目录和导航 UI。Backend 不应为了隔离组件预览伪造业务路由。

## 6. 获取远程模块源码

### `GET /internal/runtime/preview-artifacts/{artifact_id}/modules?path={logical_module_path}`

#### 请求示例

```http
GET /internal/runtime/preview-artifacts/rel_20260411_001/modules?path=src%2Fviews%2Fproject%2FHomePage.vue
Authorization: Bearer <RuntimeServiceAccessToken>
x-runtime-preview-context: <PreviewContextToken>
Accept: text/plain
```

#### 成功响应

- `200 text/plain`
- body 为 `.vue` SFC 源码

#### 失败响应建议

```json
{
  "code": "MODULE_NOT_FOUND",
  "message": "Module src/views/project/HomePage.vue not found in preview artifact rel_20260411_001"
}
```

## 7. PreviewContextToken Claims

Runtime 至少依赖以下声明：

- 公共字段
  - `tenant_id`
  - `artifact_id`
  - `preview_kind`
  - `scope_type`
  - `workspace_id`
  - `entry_descriptor`
  - `asset_base_url`
  - `trace_id`
  - `iat`
  - `exp`
  - `jti`
- 项目/页面预览额外要求
  - `project_id`
- 组件预览可选字段
  - `component_preview_mode`
  - `component_source`
  - `component_code`
  - `component_version_no`
  - `runtime_kit_component_name`
  - `runtime_kit_manifest_version`

#### 关键约束

- 组件预览 token **不要求 `project_id`**
- `scope_type=project` 时必须携带 `project_id`
- `scope_type=workspace_component` 时必须携带 `component_code` 与 `component_version_no`
- `scope_type=runtime_kit_component` 时必须携带 `component_source=runtime_kit`、`runtime_kit_component_name` 与 `runtime_kit_manifest_version`
- Runtime 后续远程模块请求不再恢复 preview session，而是直接透传 `ctx=<PreviewContextToken>`

## 8. Runtime Kit Capability API

Backend 管理端应直接读取 Runtime Kit manifest 中 `capability.enabled=true` 的条目作为 capability 目录，不写入 `workspace_components`，也不新增数据库表。该目录同时服务 Backend、Editor 和后续 Agent。

Runtime Kit capability 目录只包含 Backend/Agent 无法直接稳定实现的运行时能力，不混入通用内容块、卡片、布局辅助、页头页脚、分页 UI、目录 UI 或默认页面模板。页面结构和样式由 Backend/Agent 直接生成。

能力项支持四种 `kind`：

- `component`：可作为页面或工作空间组件源码中的 Vue 组件使用。
- `composable`：可作为源码生成时的 Vue composable 使用，只提供文档。
- `util`：可作为普通工具函数使用，只提供文档。
- `type`：可作为 TypeScript 类型导入，只提供文档。

能力项使用三个公开分组：

- `asset`：资源 URL 解析和特殊资源渲染。
- `page`：页面真实尺寸、路由、页码和导航上下文。
- `runtime`：图标、主题色解析、DOM 连线等依赖 Runtime 配置或浏览器状态的能力。

`capability.recommendation_level` 用于 Agent 排序：

- `default`：可进入常规推荐流。
- `advanced`：只在用户明确需要高级能力时推荐。
- `internal-only`：保留给内部说明，不应生成给页面源码。

`category` 只承担一级分组职责；高级能力通过 `recommendation_level=advanced` 标识，不再额外使用 `advanced` 分类。`tags` 只保留搜索语义，不重复 `category`、`kind`、`previewable` 或 `recommendation_level` 已经表达的信息。

### API 列表

- `GET /api/admin/runtime-kit/components`
  - 兼容路径：`GET /api/admin/runtime-kit/capabilities`
  - Query：`keyword`、`category`、`kind`、`base_name`、`version_no`、`include_all_versions`、`previewable`
  - 返回：Runtime Kit capability 列表；默认只返回每个 `kind + base_name` 的最新版本
- `GET /api/admin/runtime-kit/components/{name}`
  - 兼容路径：`GET /api/admin/runtime-kit/capabilities/{name}`
  - 返回单个 capability 详情
- `POST /api/admin/runtime-kit/components/{name}/preview-artifacts`
  - 兼容路径：`POST /api/admin/runtime-kit/capabilities/{name}/preview-artifacts`
  - 入参：`workspace_id`、可选 `preview_options`
  - 返回标准 `PreviewArtifactResponse`
  - 仅允许 `kind=component && previewable=true`

### 查询参数

| 参数          | 类型                                      | 说明                                                                                                                        |
| ------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `keyword`     | `string`                                  | 按 `name`、`display_name`、`summary`、`description`、`tags`、`usage`、`returns`、`return_example`、`constraints` 模糊搜索。 |
| `category`    | `string`                                  | 按 manifest 中的 `category` 精确过滤，例如 `asset`、`page`、`runtime`。                                                     |
| `kind`        | `component \| composable \| util \| type` | 按能力类型过滤。                                                                                                            |
| `base_name`   | `string`                                  | 按未带版本的能力基名过滤，例如 `Icon`、`usePageSize`。                                                                       |
| `version_no`  | `integer`                                 | 按整数版本号过滤，可用于查看历史版本。                                                                                      |
| `include_all_versions` | `boolean`                         | 为 `true` 时返回全部历史版本；缺省时只返回最新版本。                                                                        |
| `previewable` | `boolean`                                 | 过滤是否可创建预览 artifact；非组件能力固定为 `false`。                                                                     |

### 响应字段语义

| 字段                   | 类型                                      | 语义                                                                                                 |
| ---------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `kind`                 | `component \| composable \| util \| type` | 能力类型，决定 Editor 展示形态和 Backend 是否允许创建预览。                                          |
| `base_name`            | `string`                                  | 未带版本的能力基名，例如 `Icon`。                                                                    |
| `version_no`           | `integer`                                 | 整数版本号，例如 `1`。                                                                               |
| `name`                 | `string`                                  | manifest 内唯一版本化能力名，例如 `Icon.v1`，也是详情和预览接口的 `{name}`。                         |
| `import_path`          | `string`                                  | 页面或工作空间组件源码中应使用的版本化导入路径，必须来自 Runtime Kit manifest。                      |
| `category`             | `string`                                  | 能力分类，用于列表过滤和 Editor 分组，只应使用 `asset`、`page`、`runtime`。                          |
| `description`          | `string`                                  | 简短职责说明。                                                                                       |
| `display_name`         | `string`                                  | 面向用户展示的名称；缺省时可回退 `name`。                                                            |
| `summary`              | `string`                                  | 更完整的使用摘要，面向 Backend/Editor/Agent。                                                        |
| `tags`                 | `string[]`                                | 搜索和能力推荐标签。                                                                                 |
| `previewable`          | `boolean`                                 | 是否允许创建预览 artifact；只有 `component` 能力可以为 `true`。                                      |
| `preview_schema`       | `object \| null`                          | 复用组件预览 schema，用于 props/slots/mocks/presets 调参。仅对 `previewable=true` 的组件有运行意义。 |
| `preview_options`      | `object \| null`                          | 组件预览页面与组件占位默认选项，包含 `page` 与 `placement`。                                        |
| `usage`                | `string[]`                                | 调用示例，doc-only 能力必须提供。                                                                    |
| `returns`              | `string \| null`                          | composable/util/type 的返回值或导出结果说明。                                                        |
| `return_example`       | `string[]`                                | 返回值示例，composable/util/type 必须提供；建议用代码行展示 `.value`、函数返回值或关键字段。         |
| `constraints`          | `string[]`                                | 使用边界，例如依赖 Runtime 上下文、不能用于预览缩放、资源名必须存在等。                              |
| `audiences`            | `backend[] \| agent[]`                    | 能力说明面向的消费者；当前支持 `backend`、`agent`。                                                  |
| `recommendation_level` | `default \| advanced \| internal-only`    | Agent 推荐等级，用于默认推荐、高级能力和内部保留能力排序。                                           |
| `manifest_version`     | `string`                                  | Runtime Kit manifest 版本，用于 preview token 与 artifact manifest 一致性校验。                      |

### 列表响应示例

```json
{
  "items": [
    {
      "kind": "component",
      "base_name": "DefaultContainer",
      "version_no": 1,
      "name": "DefaultContainer.v1",
      "import_path": "@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue",
      "category": "page",
      "description": "页面真实画布容器，负责页面宽高和内容裁剪。",
      "display_name": "默认页面画布",
      "summary": "页面推荐根容器，负责页面实际尺寸而不是预览缩放。",
      "tags": ["canvas", "page-size"],
      "previewable": true,
      "recommendation_level": "default",
      "preview_schema": {
        "slots": {
          "default": {
            "label": "默认内容",
            "default": []
          }
        }
      },
      "preview_options": {
        "placement": {
          "width_mode": "percent",
          "width_value": 100,
          "height_mode": "percent",
          "height_value": 100,
          "horizontal_align": "center",
          "vertical_align": "center",
          "padding": 0
        }
      },
      "usage": [],
      "returns": null,
      "return_example": [],
      "constraints": [],
      "audiences": [],
      "manifest_version": "1.0.0"
    },
    {
      "kind": "composable",
      "base_name": "usePageSize",
      "version_no": 1,
      "name": "usePageSize.v1",
      "import_path": "@runtime-kit/public/composables/page/usePageSize.v1",
      "category": "page",
      "description": "读取当前页面尺寸与标准页面画布样式。",
      "display_name": "页面尺寸读取",
      "summary": "返回 width/height/aspectRatio/pageStyle。",
      "tags": ["page-size"],
      "previewable": false,
      "recommendation_level": "default",
      "preview_schema": null,
      "preview_options": null,
      "usage": [
        "import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'",
        "const { width, height, pageStyle } = usePageSize()"
      ],
      "returns": "对象：width、height、aspectRatio、pageStyle。",
      "return_example": [
        "const { width, height, pageStyle } = usePageSize()",
        "width.value // 1920",
        "height.value // 1080",
        "pageStyle.value // { width: '1920px', height: '1080px', position: 'relative', overflow: 'hidden' }"
      ],
      "constraints": ["用于页面内容层，不处理预览缩放。"],
      "audiences": ["backend", "agent"],
      "manifest_version": "1.0.0"
    }
  ],
  "total": 2
}
```

### 预览创建约束

`POST /preview-artifacts` 只允许 `kind=component && previewable=true` 的能力。Backend 应在创建 artifact 前拒绝以下情况：

- 未找到能力：`404 RUNTIME_KIT_CAPABILITY_NOT_FOUND`
- 非组件、doc-only 组件或 `previewable=false`：`400 RUNTIME_KIT_CAPABILITY_PREVIEW_NOT_ALLOWED`
- `preview_schema` 非法：`500 RUNTIME_KIT_COMPONENT_CAPABILITY_INVALID`

Runtime Kit 组件预览 artifact 必须满足：

- `owner_scope.scope_type=runtime_kit_component`
- `manifest.modules={}`
- `component_preview.component_source=runtime_kit`
- `component_preview.component_import_path` 指向 `@runtime-kit/public/...` 版本化公开组件路径
- `component_preview.placement` 包含组件占位配置，且不包含旧 `canvas` 字段
- token 与 manifest 同时携带 `runtime_kit_component_name` 和 `runtime_kit_manifest_version`

## 9. Editor 内建能力展示约定

Editor 的“内建能力”入口消费同一份 Runtime Kit capability 目录，不直接读取 Runtime 文件系统，不把能力写入工作空间组件库。

### 列表与过滤

- 必须提供 `kind` 筛选：全部、组件、Composables、Utils、Types。
- 必须提供 `category` 筛选，分类来自 API 返回的 `category`。
- 搜索框应使用本地过滤或 API `keyword`，匹配名称、导入路径、摘要、标签和调用说明。
- 能力卡片必须展示 `display_name`、`kind`、`category`、`import_path`、`summary/description`、`tags`。

### 可预览组件

当 `previewable=true` 时：

- 卡片点击进入只读预览弹窗。
- 允许复用组件预览 iframe、调参面板、预设、预览页面尺寸、页面视觉规格、主题配置和组件占位配置。
- 依赖路由或 Runtime config 的组件应以 manifest `preview_schema` 中的静态默认值作为隔离预览输入，不在组件预览中伪造项目路由。
- 不显示源码编辑、保存、发布、版本历史、恢复版本等工作空间组件操作。
- 页面尺寸、页面视觉规格或主题变更通过 `preview_options.page` 重新创建 artifact；组件占位变更通过 postMessage 更新 iframe。

### Doc-only 能力

当 `previewable=false` 时：

- 卡片点击进入文档详情弹窗。
- 只展示 `import_path`、`usage`、`returns`、`return_example`、`constraints`、`audiences`。
- 不显示预览按钮、iframe、调参面板、编辑、保存、发布、版本历史。
- `Connector`、所有 `composable`、`util`、`type` 默认按 doc-only 处理。
- `recommendation_level=advanced` 的能力应在列表中弱化展示，只在用户或 Agent 任务明确需要时推荐。
- Agent 后续也应读取这些字段生成调用建议，不应引用 `@runtime-kit/internal/...`。

## 10. 资源访问

推荐方式：

- 在 token 中通过 `asset_base_url` 指定资源根地址
- manifest 的 `assets` 存储相对资源路径
- Runtime 通过 `asset_base_url + manifest.assets[key]` 拼出最终资源 URL

## 11. 状态码建议

- `200`：成功
- `400`：请求参数非法
- `401`：RuntimeServiceAccessToken 或 PreviewContextToken 无效
- `403`：token、artifact、scope 或入口描述不匹配
- `404`：artifact、模块或资源不存在
- `409`：artifact 状态不允许访问
- `500`：内部错误

## 12. 对接检查清单

- 是否能生成符合契约的 `PreviewContextToken`
- 是否已暴露 JWKS 地址
- 是否实现 `preview-artifacts/manifest/config-bundle/modules` 接口
- 是否校验 RuntimeServiceAccessToken 与 PreviewContextToken 一致性
- 是否保证组件预览不要求 `project_id`
- 是否保证 Runtime Kit doc-only 能力不能创建预览 artifact
- 是否保证 Editor 对 doc-only 能力不展示预览、编辑、发布和历史操作
- 是否保证 artifact 按 TTL 清理，而不是持久化为可恢复会话
