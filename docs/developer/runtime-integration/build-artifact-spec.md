# 构建产物规格

构建产物是 Runtime 基于 Backend build snapshot 生成并回传的静态文件集合。

## 产物来源

Backend 创建构建任务和 build snapshot，Runtime 拉取 snapshot 后生成临时入口并执行 Vite 构建。构建完成后，Runtime 将产物压缩并上传回 Backend。

## Backend 职责

- 保存构建任务状态。
- 保存或托管构建产物。
- 提供稳定下载或静态访问地址。
- 记录失败原因和必要诊断信息。

## Runtime 职责

- 基于 snapshot 构建，不读取漂移状态。
- 输出可由 Backend 托管的静态产物。
- 回传构建日志摘要和失败信息。

## 契约测试

构建产物结构变化时，应更新 `tests/contracts/runtime-backend/release-artifact-spec.test.ts` 和 Runtime 自身集成文档。
