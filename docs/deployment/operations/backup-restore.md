# 备份与恢复

生产环境备份应覆盖数据库、资源文件、构建产物、密钥和**与数据匹配的版本信息**。只备份容器镜像或只备份数据库，都不能证明平台可恢复。完整清单、恢复顺序、RPO/RTO 目标与隔离演练入口见下文；对应架构项 AR-06 / W06，验收以 M07 为准。

## 1. 备份清单（缺一不可）

| 类别 | 内容 | 落盘位置 / 方式 | 恢复验证点 |
| :--- | :--- | :--- | :--- |
| **数据库** | 用户、工作空间、项目、页面、资产元数据、AI 会话、构建任务 | PostgreSQL：[`pg-backup.sh`](../../../deploy/scripts/pg-backup.sh)（`pg_dump -Fc`）；SQLite：完整 `lite-data` volume | 登录、读页、列表非空 |
| **资源与产物** | 用户上传、截图、构建 ZIP | local：`backend-data` / `lite-data` volume；S3：bucket 对象 | 资源可下载、构建入口可打开 |
| **AI 密钥** | `AI_SECRET_ENCRYPTION_KEY`（Fernet） | 密钥管理器 / secret 文件，**禁止**只存于内存 | 读取并解密一条用户模型凭证 |
| **签名与服务凭证** | `RUNTIME_RSA_*`、`RENDER_SERVICE_CREDENTIAL`、`RUNTIME_BUILD_WORKER_CREDENTIAL`、DB/Redis/S3 密码 | secret 文件（`deploy/secrets/`）+ 异地副本 | 预览票据可验签；Worker 可领取 |
| **版本绑定** | 镜像 tag/digest、Git SHA、`alembic_version`、Runtime `runtime_kit_version`/`build_id` | 备份 `manifest.txt` / 运维台账 | 启动镜像与 `alembic_version` 匹配 |
| **配置** | `deploy/.env`、`runtime.env`、compose 覆盖 | 与备份同周期归档（脱敏副本可只存变量名清单） | 按文档可复原拓扑 |

### 1.1 SQLite 轻量单容器

`lite-data` volume 同时保存 SQLite 数据库、本地资源、截图、构建产物和 Runtime RSA 私钥。备份时应完整备份该 volume；只复制 `web_presentation.db` 会遗漏资源文件和密钥。

容器运行中备份 SQLite 文件时，应同时复制 `web_presentation.db`、`web_presentation.db-wal` 和 `web_presentation.db-shm`；更推荐先停止容器或使用 volume 级快照。定时基线与 Demo 重置使用 [`sqlite-demo-backup.sh`](../../../deploy/scripts/sqlite-demo-backup.sh) / [`sqlite-demo-restore.sh`](../../../deploy/scripts/sqlite-demo-restore.sh)。

### 1.2 PostgreSQL 与本地资源

```bash
# 导出数据库 + alembic_version + SHA256SUMS + manifest
sudo sh ./deploy/scripts/pg-backup.sh
# 可选：设置 PGHOST/PGPORT/PGUSER 备份外部或独立运行的 PostgreSQL 实例
```

同周期备份 `backend-data` volume（或宿主机数据目录）与 `deploy/secrets/`。S3 模式改为使用 bucket 版本化/复制，并记录 `S3_*` 与 `S3_PUBLIC_BASE_URL`。

## 2. AI 密钥

`AI_SECRET_ENCRYPTION_KEY` 用于加密用户模型凭证。恢复环境必须使用同一个值，否则历史凭证无法解密。该值不是 API Key，必须是 32 字节随机值的 URL-safe base64 编码；**更换前必须先做密文迁移**，不能只改环境变量。

## 3. 备份一致性与顺序

**写入顺序（备份）：**

1. 记录开始时间、镜像 digest、Git SHA。
2. 备份数据库（`pg-backup.sh` 或 SQLite volume 快照）。
3. 备份资源/产物（`backend-data` 或 S3 一致性快照）。
4. 备份密钥与 `.env`（校验可解密一条 AI 凭证）。
5. 写 `manifest.txt`：时间、`alembic_version`、各文件校验和、操作者。

**恢复顺序（严格按序，不可颠倒）：**

1. 准备隔离环境（见 §5），确认目标**不是**生产。
2. 恢复数据库（[`pg-restore.sh`](../../../deploy/scripts/pg-restore.sh) 或完整 `lite-data`）。
3. 恢复资源和构建产物到同一存储驱动配置。
4. 恢复 `.env` 与密钥（`AI_SECRET_ENCRYPTION_KEY`、RSA、服务凭证）。
5. 启动与数据库 `alembic_version` **匹配**的平台/Runtime/Renderer 镜像。
6. 执行 §6 验证清单；记录实际 RPO/RTO。

数据库先于资源恢复，避免出现「有元数据无文件」或反向的中间态被用户看到。密钥必须在启动前就位，否则 Backend 可能以不可用状态起来。

## 4. RPO / RTO 目标

| 指标 | 含义 | 开跑前必须锁定的目标（示例，M07 前由运维确认） |
| :--- | :--- | :--- |
| **RPO** | 可接受的数据丢失窗口 | 演练用备份与事故间隔；正式环境建议 ≤ 24h（每日备份）或按业务定 |
| **RTO** | 从恢复开始到业务可验证通过的时间 | 小团队 Lite：≤ 2h；含资源回填的完整恢复在 M07 记录实测 |

**未在 M07 前锁定的数字不得写入对外承诺。** 演练产物只标「探索性基线」。

## 5. 隔离恢复演练入口（可重复）

目标：在不碰生产数据的前提下，用同一套脚本反复验证「备份集完整、恢复后业务可用」。

1. 准备独立的演练数据库（例如启动独立的临时 PostgreSQL 容器）并执行恢复：

   ```bash
   # 启动演练用临时 PostgreSQL 实例
   docker run -d --name wp-postgres-drill -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -p 55432:5432 postgres:16-alpine

   # 配置演练环境变量并执行恢复
   export PGHOST=127.0.0.1
   export PGPORT=55432
   export PGUSER=postgres
   export PGPASSWORD=postgres
   export RESTORE_DATABASE=web_presentation_drill
   export BACKUP_DIR=/var/backups/web-presentation/<TIMESTAMP>
   sh ./deploy/scripts/pg-restore.sh
   ```

2. 随后按本部署模板启动服务（仍使用 `COMPOSE_PROJECT_NAME=wp-recovery-drill`），数据卷必须是**新建**的，不得复用生产 volume 名。
3. 跑 §6 清单，把日志、耗时与截图写入 `../../archive/architecture-2026-09/runs/<date>-<sha>/summary.md`。
4. 清理仅限本轮创建的 project/volume/库；保留备份集。

SQLite 演练：复制 `lite-data` 到独立目录，用 `DATA_MOUNT_PATH`/`BACKUP_FILE`/`COMPOSE_PROJECT_NAME` 覆盖 `sqlite-demo-restore.sh` 指向演练部署。

## 6. 恢复后验证清单（不能只验 DB）

| 步骤 | 动作 | 通过标准 |
| :--- | :--- | :--- |
| 1 | 登录既有账号 | 会话建立，工作空间列表正确 |
| 2 | 打开一个项目与页面 | 源码/版本号与备份前一致 |
| 3 | 访略访问 | 上传图片/PDF 可预览下载 |
| 4 | AI 设置 | 用户模型凭证可解密（证明 `AI_SECRET_ENCRYPTION_KEY` 一致） |
| 5 | 预览 | 页面预览可打开 |
| 6 | 截图 | 远程截图产出可解码 PNG |
| 7 | 构建 | 构建 ZIP 可下载且入口可加载 |
| 8 | 版本 | `alembic_version` 与运行镜像匹配；无 `Can't locate revision` |

任一步失败即整次恢复记「未通过」，保持 AR-06 开放。

## 7. 负例（必须清晰失败）

- 缺资源文件：页面报资源 404，不得静默空白。
- 错误 `AI_SECRET_ENCRYPTION_KEY`：凭证解密失败，明确错误。
- 镜像早于 DB revision：启动报 `Can't locate revision identified by '…'`。
- 备份校验和不匹配：`pg-restore.sh` 拒绝恢复。

## 8. 回滚步骤

1. 若恢复到错误目标，停止演练 project，删除演练 volume/库（勿动生产）。
2. 若生产误恢复，立即停止写入，从**更早**的备份集再恢复，并评估 RPO 损失。
3. 保留全部操作日志与 `manifest.txt`，作为审计与复盘输入。

## 9. 相关脚本与文档

- [`deploy/scripts/pg-backup.sh`](../../../deploy/scripts/pg-backup.sh) / [`pg-restore.sh`](../../../deploy/scripts/pg-restore.sh)
- [`deploy/scripts/sqlite-demo-backup.sh`](../../../deploy/scripts/sqlite-demo-backup.sh) / [`sqlite-demo-restore.sh`](../../../deploy/scripts/sqlite-demo-restore.sh)
- [升级与回滚](./upgrade-rollback.md)、[版本兼容矩阵](../production/compatibility-matrix.md)
