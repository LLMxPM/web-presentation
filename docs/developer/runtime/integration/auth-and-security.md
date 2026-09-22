# 鉴权与安全契约

本文档定义 Browser、Backend、Runtime 在无状态预览链路中的鉴权边界，以及 Runtime 访问 Backend 内部 artifact 接口时的安全约束。

## 1. 总体原则

- 用户身份与权限只由 Backend 负责校验。
- Runtime 不维护用户体系，不解析浏览器 Cookie/JWT。
- 预览上下文统一使用短生命周期 `PreviewContextToken`。
- Preview 为无状态链路，不保存也不恢复 preview session。
- 预览产物访问必须同时绑定 token 中的 `artifact_id`、`preview_kind`、`scope_type` 与入口描述。

## 2. Browser -> Backend

- Browser 使用平台已有登录态访问 Backend 公开预览入口。
- Backend 校验：
  - 用户是否登录
  - 用户是否属于目标租户
  - 用户是否有目标项目或工作空间权限
  - 用户是否有目标 preview artifact 的访问权限
- Backend 校验通过后，反向代理到 Runtime `/__preview`，并透传预览上下文 token。

## 3. Backend -> Runtime

Backend 代理到 Runtime 时，必须注入：

- 请求头：`x-runtime-preview-context: <PreviewContextToken>`

Runtime 通过 `RUNTIME_PREVIEW_JWKS_URL` 获取 JWKS 并离线验签。

### PreviewContextToken 必填声明

- `iss`
- `aud`
- `sub`
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

### 按场景裁剪的附加声明

- 项目/页面预览额外要求：
  - `project_id`
- 组件预览可选：
  - `component_preview_mode`
  - `component_source`
  - `component_code`
  - `component_version_no`
  - `runtime_kit_component_name`
  - `runtime_kit_manifest_version`

组件预览约束：

- `scope_type=workspace_component` 时必须携带 `component_code` 与 `component_version_no`。
- `scope_type=runtime_kit_component` 时必须携带 `component_source=runtime_kit`、`runtime_kit_component_name` 与 `runtime_kit_manifest_version`。

### 验签失败处理

- Token 缺失：`401 PREVIEW_CONTEXT_REQUIRED`
- Token 声明不完整：`401 PREVIEW_CONTEXT_INVALID`
- Token 过期或签名非法：`401`
- manifest 与 token 的租户、artifact、scope 或入口描述不一致：`403 MANIFEST_CONTEXT_MISMATCH`

## 4. Runtime -> Backend

Runtime 调用 Backend 内部 preview artifact API 时，统一使用服务级 JWT，并继续透传原始预览上下文：

- `Authorization: Bearer <RuntimeServiceAccessToken>`
- `x-runtime-preview-context: <PreviewContextToken>`

Backend 应同时校验：

- 服务身份是否合法
- `aud` 是否匹配内部 API 约定
- 当前请求的 `artifact_id` 是否与 token 一致
- token 中的 `preview_kind / scope_type / entry_descriptor` 是否与 manifest 一致
- 当前服务是否被允许读取该租户下对应 scope 的 preview artifact

## 5. 资源与模块白名单

Runtime 对远程模块和资源采用双层约束：

### 第一层：预览上下文约束

- 当前请求必须属于同一个 `tenant_id + artifact_id`
- 项目/页面预览还必须匹配 `project_id`
- 组件预览不得额外要求 `project_id`
- Runtime Kit 内建组件预览必须匹配 manifest 中的 `runtime_kit_component_name` 与 `runtime_kit_manifest_version`

### 第二层：manifest 白名单

- 普通远程模块必须存在于 `manifest.modules`
- 单页面预览的入口模块允许不进入 `manifest.modules`，但豁免范围仅限 token 中声明的 `entry_descriptor.module_path`
- Runtime Kit 内建组件预览不写入远程模块，`manifest.modules` 必须为空对象
- Runtime Kit 内建组件预览只能面向 `kind=component && previewable=true` 的 capability
- Runtime Kit doc-only 能力不生成 preview artifact，也不应获得 `scope_type=runtime_kit_component` 的预览 token
- 页面、工作空间组件和 previewSchema 只能引用 Runtime Kit manifest 公开的版本化路径；禁止引用 `@runtime-kit/internal/...` 和未带 `.vN` 的 `@runtime-kit/public/...`
- 静态资源应优先命中 `manifest.assets`

## 6. 错误码建议

| HTTP | code | 含义 |
| --- | --- | --- |
| 401 | `PREVIEW_CONTEXT_REQUIRED` | 缺少预览上下文 token |
| 401 | `PREVIEW_CONTEXT_INVALID` | 预览上下文声明不完整或非法 |
| 403 | `MANIFEST_CONTEXT_MISMATCH` | manifest 与预览上下文不一致 |
| 403 | `PREVIEW_ARTIFACT_MISMATCH` | token 与请求的 artifact 不一致 |
| 403 | `SCOPE_CONTEXT_MISMATCH` | 项目/工作空间归属与 token 不一致 |
| 404 | `ARTIFACT_NOT_FOUND` | preview artifact 不存在 |
| 404 | `MODULE_NOT_FOUND` | 模块不存在 |
| 404 | `RUNTIME_KIT_CAPABILITY_NOT_FOUND` | Runtime Kit capability 不存在或未启用 |
| 400 | `RUNTIME_KIT_CAPABILITY_PREVIEW_NOT_ALLOWED` | Runtime Kit capability 是 doc-only 或不允许预览 |
| 5xx | `BACKEND_REQUEST_FAILED` | Runtime 调用 Backend 内部 API 失败 |

## 7. 安全建议

- `RuntimeServiceAccessToken` 应由 Backend 在发起 preview/build 请求时短期签发，并通过内网请求头下发给 Runtime。
- `PreviewContextToken.exp` 建议控制在分钟级。
- `jti` 仅用于链路追踪与审计，不承载会话恢复语义。
- Runtime 和 Backend 间建议走内网或 Service Mesh。
- 如平台支持，建议叠加 mTLS。
