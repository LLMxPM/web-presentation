# 升级与回滚

升级和回滚必须同时考虑平台、Runtime、Renderer 镜像、数据库迁移和配置变量。支持组合与摘流边界见[版本兼容矩阵](./compatibility-matrix.md)。本轮 M05 固定 N-1=`4c7eee8`，N 为 `73b0036` 加迁移事务修复；完整旧 platform/Lite 入口、真实 PG/SQLite 前滚及应用回滚通过，见[实机记录](../../temp/runs/2026-10-01-73b0036/summary.md)。这一组合采用**排空、停旧实例、独立迁移、启动新实例**，不能在删列迁移期间混跑。

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
| 预览多副本 | **同版池替换 / 跨版整池切换** | 新池核对发布身份；旧池停止新入口并有界排空，再整体切流 |
| 构建/检查角色 | **排空后替换** | 等在途任务或租约过期；attempt 围栏防迟到上传 |
| Backend 多副本 | **排空停旧、先迁移后启动** | 共享密钥环/DB/存储；当前迁移先删旧 ORM 列，再由补偿恢复，旧实例不能穿过迁移窗口；普通 AI Run 不迁移 |

推荐顺序（M05 实测）：

1. 停止新的业务写入，排空普通 Run、页面/组件/图片外部任务与构建/截图；Worker 摘除前运行只读 `app.scripts.check_render_worker_removal`，不得仅看健康接口。
2. 停止全部旧 Backend，备份 DB、资源、产物与密钥。
3. 用 **N 镜像的独立迁移器**执行一次 `alembic upgrade head`，核对目标 `20260930_0300`。`20260930_0200` 恢复旧 ORM 所需兼容列，但默认 0 不能恢复删列前的历史值。
4. 启动 N Backend；platform/Lite 可关闭入口自动迁移，由独立迁移器负责。按同版池与排空策略替换 Runtime/Renderer。
5. 验证真实业务链路后恢复流量。补偿后的旧应用能回退运行，是应用回滚证据，不是迁移中混跑或无中断滚动的承诺。

生产 env 版命令：

```bash
cd deploy
docker compose -f compose/compose.prod.yml pull
docker compose -f compose/compose.prod.yml up -d
```

production env 版会先运行 `backend-migrate`。上述 `up` 依赖不能自动排空已经运行的旧 Backend，升级前仍须完成前述停旧步骤。迁移成功后再启动 Backend、Runtime、Renderer 和 Gateway。最终模板与远端发布矩阵仍由 M06 验收，不能把本地专属拓扑结果当作生产发布通过。

## 迁移中断

PG 迁移保持事务回滚；SQLite 的独立 Alembic 引擎显式接管 `BEGIN`，使 DDL 与 revision 在同一事务内提交。真实迁移容器 SIGKILL，以及子进程在 ADD/DROP DDL 执行后直接退出的回归，均证明修复后的 SQLite 不会留下新列与旧 revision 的半迁移状态。该设置只作用于迁移引擎，不改变业务 Session。

中断后先核对 revision、实际列与迁移日志，再用同一 N 迁移器重试。历史未修复的 SQLite 镜像可能留下 orphan 列，本轮已复现；遇到这种状态应隔离业务、保存证据，并从一致备份恢复或执行限定范围的维护补偿。不得通过 `stamp` 掩盖，也不能假定直接重试会成功。本轮负例恢复只使用本次演练专属快照，不构成生产 RPO/RTO 验收。

## 回滚

如果需要回滚，平台、Runtime 和 Renderer 镜像应一起回滚到兼容版本。

本次约定的回滚是**保留新 schema、回退应用镜像**。先由 N 迁移器前滚到含补偿列的 head，再停 N 应用；回退完整 `4c7eee8` platform/Lite 镜像，分别设置 `PLATFORM_SIMPLE_RUN_MIGRATIONS=false` / `PLATFORM_LITE_RUN_MIGRATIONS=false`。旧入口默认开启迁移时，会因未知 revision 非零退出；关闭后，两种数据库均通过历史数据读写、真实页面任务取消与自动 deferred 续跑。

不要把降到删列 revision 当成应用回滚步骤，也不要用 `alembic stamp` 覆盖版本号。需要数据库恢复时，单独按一致备份与恢复方案执行，并接受相应数据恢复边界。兼容列保留至旧实例退出且回滚窗口结束后再评估删除。

## 验证

升级或回滚后至少验证：

- 登录和会话。
- 工作空间、项目和页面读取。
- 资源访问。
- 页面预览和截图。
- 项目构建和产物访问。
- AI 设置读取、真实页面写工具入队、取消及自动 deferred 续跑；消费后完整 Task result 清空。
