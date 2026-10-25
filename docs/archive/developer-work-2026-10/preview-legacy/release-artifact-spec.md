# Preview Artifact 规范

本文档定义 Runtime 所依赖的 preview artifact 结构与命名规范。artifact 是短生命周期、不可恢复的临时预览快照。

## 1. 设计目标

- 预览内容在 artifact 生命周期内保持不可变。
- 可按 `tenant_id + artifact_id` 精确定位。
- 可被 Runtime 按需拉取模块与资源。
- 配置、入口、模块、资源之间通过 manifest 建立稳定映射。

## 2. 产物组成

每个 preview artifact 至少应包含四类内容：

### 2.1 manifest

用于描述 artifact 元数据、入口描述、模块白名单和资源映射。

必填字段：

- `artifact_id`
- `tenant_id`
- `preview_kind`
- `owner_scope`
- `entry_descriptor`
- `modules`
- `assets`

可选字段：

- `version`
- `published_at`

### 2.2 config-bundle

标准化 JSON 配置包，包含：

- `app`
- `routes`
- `icons`
- `themes`
- `fonts`
- `module_resolver`

组件预览额外包含：

- `component_preview`

要求：

- 字段结构应与 Runtime 当前的配置读取逻辑兼容。
- 不再要求浏览器直接读取 YAML。
- 由 Backend 在创建 artifact 时完成 YAML -> JSON 的标准化。
- `module_resolver` 必须包含 `remote_component_prefix`、`runtime_kit_alias`、`runtime_kit_manifest_version` 与 `runtime_kit_exports`，其中 `runtime_kit_exports` 来自 Runtime Kit manifest。
- `runtime_kit_exports` 是 Runtime Kit 公开导入边界的完整快照，可包含 `component/composable/util/type`，能力分组仅使用 `asset`、`page`、`runtime`。高级能力通过 `capability.recommendation_level=advanced` 标识。只有 `kind=component && capability.previewable=true` 的能力可创建组件预览 artifact。
- Runtime Kit 只承载 Backend/Agent 无法直接稳定实现的运行时能力，不应混入通用内容块、布局辅助、默认页面模板或样式组件。

### 2.3 模块源码

- 页面模块与组件模块均以源码文本形式存储。
- 逻辑路径统一为 `src/...` 形式。
- 路由配置中的 `component` 字段可继续使用 `@/...` 形式，Runtime 会在加载前规范化。
- 页面/组件源码引用 Runtime 基础能力时只允许使用 `@runtime-kit/...` manifest 公开的版本化路径；`@/components`、`@/layouts`、`@/core`、`@/styles` 属于 Runtime 私有路径。

### 2.4 资源索引

- 通过 `assets` 建立逻辑路径到实际资源路径的映射。
- 键统一使用规范化相对路径，例如 `img/logo/ppt-e.png`。
- 值可为：
  - 相对 `asset_base_url` 的资源路径
  - 已签名或可直接访问的绝对 URL

## 3. owner_scope 规则

`owner_scope` 用于明确 artifact 的业务归属：

### 项目/页面预览

```json
{
  "scope_type": "project",
  "workspace_id": "11",
  "project_id": "21"
}
```

### 组件预览

工作空间组件预览：

```json
{
  "scope_type": "workspace_component",
  "workspace_id": "11",
  "component_code": "CMP_DEMO",
  "component_version_no": 3,
  "preview_mode": "draft"
}
```

Runtime Kit 内建组件预览：

```json
{
  "scope_type": "runtime_kit_component",
  "workspace_id": "11",
  "runtime_kit_component_name": "Icon",
  "runtime_kit_manifest_version": "1.0.0"
}
```

关键约束：

- 项目/页面预览必须带 `project_id`。
- 组件预览不得要求 `project_id`。
- `scope_type=workspace_component` 必须携带工作空间组件编码与版本号。
- `scope_type=runtime_kit_component` 不携带工作空间组件版本号，但必须携带 Runtime Kit 组件名与 manifest 版本。

## 4. entry_descriptor 规则

`entry_descriptor` 用于描述 Runtime 首屏入口：

### 整项目预览

```json
{
  "entry_type": "route",
  "route": "/home"
}
```

### 单页面预览

```json
{
  "entry_type": "module",
  "module_path": "src/views/project/HomePage.vue"
}
```

### 组件预览

```json
{
  "entry_type": "component_host"
}
```

## 5. 模块映射规则

manifest 中的 `modules` 使用逻辑路径为 key，例如：

```json
{
  "src/workspace-components/CMP_DEMO/v/1.vue": {
    "path": "src/workspace-components/CMP_DEMO/v/1.vue",
    "hash": "sha256:abc123"
  }
}
```

要求：

- key 必须唯一。
- `path` 建议与 key 保持一致。
- `hash` 用于审计、缓存与预览追踪。
- Runtime Kit 内建组件预览的 `modules` 必须为空对象。
- Runtime Kit 内建组件预览的根组件通过 `config-bundle.component_preview.component_import_path` 指向 `@runtime-kit/public/...` 版本化本地公开组件模块。
- Runtime Kit doc-only 能力，例如 `composable/util/type` 或 `previewable=false` 组件，不生成 preview artifact，也不应出现在 `component_preview` 中。
- 页码、目录和导航能力应通过 `useCurrentPage`、`useRouteCatalog`、`usePageNavigation` 暴露为数据或控制能力，Backend/Agent 在页面源码中生成对应 UI，不应通过组件预览伪造业务路由。

## 6. 资源映射规则

```json
{
  "img/logo/ppt-e.png": "assets/logo/ppt-e.abc123.png",
  "fonts/source-code-pro.woff2": "assets/fonts/source-code-pro.def456.woff2"
}
```

要求：

- Runtime 优先命中 `assets` 映射。
- 未命中时可回退到 `asset_base_url + 原始资源路径`。
- 对于高价值资源，建议总是写入 `assets` 映射以避免歧义。

## 7. 兼容与豁免规则

- Runtime 会将 `@/views/...`、`/src/views/...`、`views/...` 统一规范化为 `src/views/...`。
- 本地内建兜底页面，如 `src/runtime-shell/fallback/NotFoundPage.vue`，仍由 Runtime 本地代码提供。
- 单页面预览的入口模块允许不进入 `manifest.modules` 白名单，但仅限 `entry_descriptor.module_path` 指向的那一个入口模块。
- 页面、工作空间组件和 previewSchema 只能引用 Runtime Kit manifest 公开的版本化路径；`@runtime-kit/internal/...`、旧 `@runtime-kit/components/...` 和未带 `.vN` 的 `@runtime-kit/public/...` 不属于公开契约。

## 8. 生命周期建议

- 建议每个 artifact 生成不可复用的 `artifact_id`。
- 建议 manifest 与 config-bundle 使用强缓存配合 TTL 清理。
- 建议模块源码和资源统一进入对象存储或带过期策略的制品存储。
- artifact 只服务当前预览链路，不视为可恢复会话。
