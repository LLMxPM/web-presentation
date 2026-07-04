# Runtime 接入架构

Runtime 是平台的数据面执行引擎，负责预览、组件预览、截图、诊断和构建。根仓通过 `runtime/` 子模块接入独立项目 `web-runtime-vue`。

## 接入方式

根仓依赖 Runtime 的公开契约，而不是依赖 Runtime 内部实现。公开契约包括：

- Runtime 服务入口和环境变量。
- Runtime Kit manifest。
- 预览上下文读取协议。
- 构建 snapshot 和 release artifact 规格。
- 容器镜像标签和发布流程。

## 子模块边界

更新 Runtime 能力应优先在 `web-runtime-vue` 独立项目完成开发、测试和镜像发布，再回到根仓更新子模块指针。根仓更新指针时，需要补充契约测试或更新文档。

## Runtime Kit

Runtime Kit 是页面源码和工作空间组件可引用的公共能力集合。能力必须进入 `runtime/src/runtime-kit/manifest/runtime-kit.manifest.json`，并使用 `<ExportName>.vN` 命名和带 `.vN` 的公开 import path。

## 平台回源

平台部署中，Runtime 通过内网 `RUNTIME_BACKEND_API_BASE_URL` 回源 Backend 读取预览上下文、资源和构建快照。浏览器访问地址由 `RUNTIME_PUBLIC_BASE_URL` 和 `RUNTIME_SERVER_BASE_PATH` 决定。

## 相关文档

- [Runtime 接入文档入口](../runtime-integration/README.md)
- [Runtime Kit 契约](../runtime-integration/runtime-kit-contract.md)
- [previewSchema 契约](../runtime-integration/preview-schema.md)
- [构建产物规格](../runtime-integration/release-artifact-spec.md)
