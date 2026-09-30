# 升级与回滚

升级和回滚必须同时考虑平台、Runtime、Renderer 镜像、数据库迁移和配置变量。支持组合、摘流顺序与 Run 收敛边界见[版本兼容矩阵](./compatibility-matrix.md)。M05 已实测 N=`a06120e` / N-1=`4c7eee8` 组合边界：**必须先 `alembic upgrade head` 再混跑或替换 Backend**；N 不可跑在 N-1 schema。

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
| Backend 多副本 | **先 migrate，再先扩后摘** | 共享密钥环/DB/存储；N-1 可短暂跑在 N schema 上；普通 AI Run 不迁移 |

推荐顺序（M05 实测）：

1. 备份 DB → `alembic upgrade head`（只跑一次）。
2. 混跑窗口：N-1 与 N Backend 可共存于 N schema（登录/业务共用同一 DB）。
3. 滚动替换 Backend，再排空替换 Runtime/Renderer（同池指纹一致）。
4. 摘除 N-1。

生产 env 版命令：

```bash
cd deploy
docker compose -f compose/compose.prod.yml pull
docker compose -f compose/compose.prod.yml up -d
```

production env 版会先运行 `backend-migrate`。迁移成功后再启动 Backend、Runtime、Renderer 和 Gateway。分角色模板按[兼容矩阵 §3](./compatibility-matrix.md#3-升级窗口与摘流策略) 逐角色替换。

## 回滚

如果需要回滚，平台、Runtime 和 Renderer 镜像应一起回滚到兼容版本。

数据库迁移一旦前进，回滚镜像时必须确认旧镜像仍包含当前 `alembic_version` 指向的 revision 文件。N-1 对 N DB 执行 `alembic upgrade/current` 会得到 `Can't locate revision identified by '…'`（预期拒绝）；N-1 **应用进程**仍可跑在 N schema 上（多余列无害）。需要回退 schema 时按 migration 的 `downgrade` 逐级执行（`20260930 → 20260929 → 20260926`），不要直接 `alembic stamp` 覆盖版本号。不可逆 migration 只能前滚或从备份恢复。

## 验证

升级或回滚后至少验证：

- 登录和会话。
- 工作空间、项目和页面读取。
- 资源访问。
- 页面预览和截图。
- 项目构建和产物访问。
- AI 设置读取和一次 mock 或真实会话。
