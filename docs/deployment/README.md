<!-- 文件功能：部署方式选择入口，引导读者按场景选择 Lite 或生产部署，并导航到子目录专题文档。 -->
# 部署指南

`web-presentation` 提供两种部署方式，按团队规模和基础设施选择。

| 方式 | 适用场景 | 基础设施 |
| :--- | :--- | :--- |
| **Lite 轻量版** | 个人创作者、5–10 人小团队、NAS 自托管 | 单容器（SQLite + memory runtime），零配置启动 |
| **生产版** | 正式上线、多人协作、高可用需求 | 多容器（PostgreSQL + Redis），分角色拓扑 |

## Lite 轻量版

| 文档 | 内容 |
| :--- | :--- |
| [快速部署总览](./lite/README.md) | 架构说明、极简启动和适用规模 |
| [Docker 命令行](./lite/docker.md) | `docker run` 和 Compose 部署 |
| [飞牛 fnOS](./lite/fnos.md) | 飞牛 NAS 图形界面部署 |
| [群晖 DSM](./lite/synology.md) | 群晖 Container Manager 部署 |
| [日常维护](./lite/maintenance.md) | 无损升级、备份还原与反代配置 |

## 生产版

| 文档 | 内容 |
| :--- | :--- |
| [生产部署指南](./production/README.md) | compose 模板、环境变量、启动和验证 |
| [Compose 部署说明](./production/compose.md) | 三个模板差异、副本扩容与滚动发布 |
| [部署环境变量](./production/env-vars.md) | 核心变量分组与关键约束 |
| [多 Backend 一致性](./production/multi-backend.md) | 共享密钥、密钥轮换与 AI Run 停机语义 |
| [版本兼容矩阵](./production/compatibility-matrix.md) | N/N-1 组合、升级窗口与摘流策略 |
| [执行隔离与权限](./production/execution-isolation.md) | 构建领取器、编译子进程边界与权限矩阵 |
| [CI/CD 与容器发布](./production/cicd.md) | 镜像构建、发布策略和 GitHub Actions |

## 运维操作

| 文档 | 内容 |
| :--- | :--- |
| [备份与恢复](./operations/backup-restore.md) | 数据库、资源、构建产物和密钥备份 |
| [升级与回滚](./operations/upgrade-rollback.md) | 镜像升级、数据库迁移和回滚 |
| [部署排障](./operations/troubleshooting.md) | 健康检查、Runtime、AI 设置和迁移问题 |
| [Lite 规模与隔离决策](./operations/lite-scale-and-isolation.md) | 推荐规模、故障域和隔离决策 |

## 发布与验证

| 文档 | 内容 |
| :--- | :--- |
| [发布检查](./release-checklist.md) | 发布待验证事项与证据状态 |

仓库根 `deploy/` 承载实际 Compose 模板、Dockerfile 和部署脚本；本目录承载使用说明和决策文档。
