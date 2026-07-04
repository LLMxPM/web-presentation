# 配置模板边界

Backend 和 Runtime 都有配置模板，但职责不同。

## Backend 配置模板

Backend 默认项目配置模板由 `backend/app/config_templates/` 自身维护。Backend 运行时代码不应直接读取 `runtime/public/config/`。

## Runtime fixture 配置

Runtime 自带的 `public/config/*.config.yaml` 仅作为 Runtime 独立运行和本地 fixture 使用，不是根仓 Backend 的运行时配置来源。

## 根仓契约测试

根仓契约测试只约束两侧模板入口和必要结构，避免 Backend 与 Runtime 因模板字段漂移导致预览或构建失败。

## 变更要求

项目配置结构变化时，需要同步 Backend 模板、Runtime fixture、契约测试和相关文档。
