# Runtime 接入架构

Runtime 是平台的数据面执行引擎，负责预览、组件预览、诊断入口和构建，源码位于主仓原生目录 `runtime/`。真实 Chromium 截图与页面诊断由独立 Renderer 执行；Runtime 为其提供受保护的页面宿主。

## 接入方式

平台依赖 Runtime 的公开契约，而不是依赖 Runtime 内部私有实现。公开契约包括：

- Runtime 服务入口和环境变量。
- Runtime Kit manifest。
- 预览上下文读取协议。
- 构建 snapshot 和 release artifact 规格。
- 容器镜像标签和发布编排。

## 模块边界与协作

Runtime 作为主仓原生微服务，与其他模块通过稳定公开契约交互：
- 页面代码与组件引用严格受限于 Runtime Kit manifest 白名单；
- 预览与构建上下文通过标准化 Backend 内部 API 交互；
- 修改 Runtime 时运行 `pnpm run test:runtime:gate` 和 `pnpm run test:contracts` 保证契约不发生漂移。

## Runtime Kit

Runtime Kit 是页面源码和工作空间组件可引用的公共能力集合。能力必须进入 `runtime/src/runtime-kit/manifest/runtime-kit.manifest.json`，并使用 `<ExportName>.vN` 命名和带 `.vN` 的公开 import path。

## 平台回源

平台部署中，Runtime 通过内网 `RUNTIME_BACKEND_API_BASE_URL` 回源 Backend 读取预览上下文、资源和构建快照。浏览器访问地址由 `RUNTIME_PUBLIC_BASE_URL` 和 `RUNTIME_SERVER_BASE_PATH` 决定。

## 相关文档

- [Runtime 接入文档入口](../runtime-integration/README.md)
- [Runtime Kit 契约](../runtime-integration/runtime-kit-contract.md)
- [previewSchema 契约](../runtime-integration/preview-schema.md)
- [构建产物规格](../runtime-integration/release-artifact-spec.md)
