# 升级与回滚

升级和回滚必须同时考虑平台镜像、Runtime 镜像、数据库迁移和配置变量。

## 升级前

- 备份 PostgreSQL。
- 备份资源和构建产物。
- 保存当前平台镜像标签、Runtime 镜像标签和 `runtime` 子模块 SHA。
- 检查 Release 说明和环境变量变化。

## 升级

```bash
cd deploy
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
```

production env 版会先运行 `backend-migrate`。迁移成功后再启动 Backend、Runtime 和 Gateway。

## 回滚

如果需要回滚，平台镜像和 Runtime 镜像应一起回滚到兼容版本。不要只回滚其中一个镜像。

数据库迁移一旦前进，回滚镜像时必须确认旧镜像仍包含当前 `alembic_version` 指向的 revision 文件。否则 Backend 可能无法启动或继续迁移。

## 验证

升级或回滚后至少验证：

- 登录和会话。
- 工作空间、项目和页面读取。
- 资源访问。
- 页面预览和截图。
- 项目构建和产物访问。
- AI 设置读取和一次 mock 或真实会话。
