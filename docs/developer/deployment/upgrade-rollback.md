# 升级与回滚

升级和回滚必须同时考虑平台、Runtime、Renderer 镜像、数据库迁移和配置变量。支持组合、摘流顺序与 Run 收敛边界见[版本兼容矩阵](./compatibility-matrix.md)；**M05 实测前不要把任一组合当作已验收**。

## 升级前

- 备份 PostgreSQL；SQLite 轻量版备份完整 `lite-data` volume。
- 备份资源、构建产物和密钥，细节见[备份与恢复](./backup-restore.md)。
- 保存当前平台、Runtime、Renderer 镜像标签和代码仓库 Git commit SHA。
- 检查 Release 说明和环境变量变化。
- 记录当前 DB `alembic_version` 与 Runtime `/__runtime_healthz` 指纹（`runtime_kit_version` / `build_id`）。

## 升级策略

| 形态 | 策略 | 摘流要点 |
| :--- | :--- | :--- |
| Lite / 单实例小团队 | **停机升级** | 先备份再迁移；接受短暂停机 |
| 预览多副本 | **滚动** | 新副本就绪 → 切流 → 旧副本排空（带上界）→ 下线 |
| 构建/检查角色 | **排空后替换** | 等在途任务或租约过期；attempt 围栏防迟到上传 |
| Backend 多副本 | 先扩后摘 | 共享密钥环/DB/存储；普通 AI Run 不迁移 |

生产 env 版命令：

```bash
cd deploy
docker compose -f compose/compose.prod.yml pull
docker compose -f compose/compose.prod.yml up -d
```

production env 版会先运行 `backend-migrate`。迁移成功后再启动 Backend、Runtime、Renderer 和 Gateway。分角色模板按[兼容矩阵 §3](./compatibility-matrix.md#3-升级窗口与摘流策略) 逐角色替换。

## 回滚

如果需要回滚，平台、Runtime 和 Renderer 镜像应一起回滚到兼容版本。

数据库迁移一旦前进，回滚镜像时必须确认旧镜像仍包含当前 `alembic_version` 指向的 revision 文件。否则 Backend 可能无法启动或继续迁移。不可逆 migration 只能前滚或从备份恢复；不要直接 `alembic stamp` 覆盖版本号。

## 验证

升级或回滚后至少验证：

- 登录和会话。
- 工作空间、项目和页面读取。
- 资源访问。
- 页面预览和截图。
- 项目构建和产物访问。
- AI 设置读取和一次 mock 或真实会话。
