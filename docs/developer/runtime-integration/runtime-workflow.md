# Runtime 运行时开发与维护

`runtime/` 是主仓库的原生演示文稿与页面运行时服务（基于 Vue 3 + Vite）。负责画布呈现、页面切换、组件预览、画布缩放、诊断入口、导出与构建执行。真实 Chromium 截图和页面诊断由独立 Renderer 执行。

## 开发与测试流程

1. 在 `runtime/` 目录下进行功能开发或样式调整。
2. 运行 Runtime 自身测试：
   ```powershell
   pnpm run test:runtime
   ```
3. 执行 Runtime 完整质量门禁（类型检查 + 单元测试 + 生产构建）：
   ```powershell
   pnpm run test:runtime:gate
   ```
4. 若改动涉及 Runtime Kit 公开能力或清单（`runtime/src/runtime-kit/manifest/runtime-kit.manifest.json`），运行根仓契约测试确保与 Backend 校验规则对齐：
   ```powershell
   pnpm run test:contracts
   ```

## 镜像与部署

- **单容器部署**：`deploy/docker/Dockerfile.lite` 会直接复制 `runtime/` 目录源码与依赖并打包进单容器镜像；
- **微服务部署**：`runtime/Dockerfile` 提供了独立的 Runtime 容器镜像定义，由平台 Docker Compose 或集群调度。

## 文档联动

Runtime 接口、环境变量、manifest、构建产物或功能能力变化时，需要同步更新：
- [`runtime/src/runtime-kit/manifest/runtime-kit.manifest.json`](../../../runtime/src/runtime-kit/manifest/runtime-kit.manifest.json)
- [`docs/developer/runtime/`](../runtime/) 业务组件与能力文档
- 本目录下的相关契约说明
