# Runtime Kit 契约

Runtime Kit 是页面源码、工作空间组件源码和 previewSchema 可以引用的公共能力集合。

## manifest

公开能力以 `runtime/src/runtime-kit/manifest/runtime-kit.manifest.json` 为单一事实源。Backend 通过该清单校验页面源码、组件源码和 previewSchema 的导入边界。

- `name = base_name.vN` 是能力标识，`import_path` 是实际模块地址；版本号必须一致，文件基名不要求等于导出符号。例如 `resolveColor.v1` 从 `utils/colors.v1` 导入，调用方不能按名称拼路径。
- `capability.enabled`、`audiences` 与说明字段控制目录披露。关闭 enabled 后目录与详情隐藏，但 exports 保留的入口及依赖身份继续兼容历史源码；禁止导入需要移除 exports 项。
- 目录默认按 `kind + base_name` 返回最新版本，旧版本通过版本参数或 `include_all_versions` 查询。`AssetModel.v1` 单一条目同时承担静态展示、组件预览与 Scene 实例句柄：非交互实例的 `ref.getHandle()` 可用，`interactive=true` 时句柄为 null。
- 顶层 `version` 是清单版本，不代替单项 `.vN` 或 `.runtime-build-id` 发布身份。预览票据及版本化资源路径继续核实发布身份。
- `model3d_engine` 是三维策略的身份快照，测试与 Runtime 的 `MODEL3D_ENGINE_POLICY` 对拍。

Backend 有进程级清单缓存，维护清单后需重启 Backend 刷新目录与写入校验；页面源码继续使用 Vite HMR。

## 预览、构建与诊断门禁

`runtime/src/core/shared/runtime-kit-import-policy.mjs` 是 Runtime 二次导入裁决的共同实现。预览使用类型化适配，项目构建和诊断 Worker 直接嵌入同一份纯 JS；Scene 策略继续由共享模块生成。

- 限制作用于远程页面、工作空间组件和构建中的创作模块，Runtime 自身可依赖内部实现。
- 同时检查原始 alias、Vite 提前展开的绝对路径、`@/runtime-kit` 与相对路径，避免 alias 先执行导致白名单失效。
- 缺省 Backend 快照时使用真实本地清单；显式空快照拒绝所有 Kit 导入。本地清单读取失败或声明版本无法核实时拒绝。
- Backend 快照与本地入口取交集，只能收紧权限。项目构建、单次诊断、常驻诊断均传递本轮快照及版本，不沿用上轮权限。
- 预览凭当前模块票据验签、核对 artifact 归属后恢复快照。缓存仅加速，冷副本不依赖先访问 HTML，缓存命中也不能代替当前请求验签。
- Kit 拒绝返回 `RUNTIME_LOCAL_IMPORT_FORBIDDEN`；Worker 保留 Vite 包装前的策略错误码，GSAP 直导继续返回 `SCENE_GSAP_IMPORT_FORBIDDEN`。

## 执行身份与目录文案

清单保留统一维护入口，发布身份与 Backend 检查指纹使用执行投影。category、description，以及 capability 下的 enabled、previewable、display_name、summary、tags、usage、returns、return_example、constraints、audiences 不参与执行身份。

公开入口、版本、preview_schema、preview_options、引擎及未知字段仍进入身份。新增字段默认保留，只有确认仅用于目录才可排除。Python 与发布脚本使用 `tests/fixtures/runtime-kit-identity-cases.json` 对拍；Backend 还将 Kit 导入策略版本放入指纹，防止本地 `dev` 发布身份掩盖规则更新。

## 命名规则

读取能力时完整保留 `import_path`、`usage`、`constraints`、`preview_schema.props`，按字段投影，不按 JSON 字符数截断。字段缺失或出现省略标记时补读详情。

`Icon.v1` 是渲染契约，平台图标名称来自当前工作空间 active 图标资源；`home` 等示例不保证存在。先查询真实资源并保留分页，再读取契约；没有合适资源时按任务授权创建 SVG 图标，使用返回的真实 `name`。独立 Runtime 仍可使用自身图标配置。

- 清单项名称必须使用 `<ExportName>.v<整数版本>`。
- 公开 import path 必须带 `.vN`。
- 不兼容演进时新增更高版本文件，不修改仍被依赖的旧版本文件。当前只保留 `useAudioCue.v1` 与 `AssetModel.v1` 两个入口：`useAudioCue` 与 `AssetModel` 的历史 v2/v3 已合并回 v1，`.v1` 对这两个能力表示当前唯一实现。

## 禁止暴露

Runtime shell 内部组件、component-preview 宿主页、PDF 导出、侧栏、缩略图、Toast、ErrorBoundary 等壳层能力不应通过 Runtime Kit 暴露给页面源码、组件源码或 AI 能力目录。

## 测试要求

Runtime Kit manifest 或公开 import path 变化时，应补充 Runtime manifest 测试和根仓 Backend 契约测试。

门禁变更还需运行 `runtime-kit-preview.integration.test.ts` 与 `runtime-kit-worker.integration.test.ts`：通过真实 Vite resolver 和三种 Worker 检查 alias、快照/版本、错误码及任务隔离。测试使用隔离目录和 Backend 网络替身，不启动业务服务、不重置业务数据；不替代 Renderer 或发布产物的浏览器验收。
