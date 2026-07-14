# 备份与恢复

生产环境备份应覆盖数据库、资源文件、构建产物和密钥。只备份容器镜像不足以恢复平台状态。

## 必备备份

- PostgreSQL 或 SQLite：用户、工作空间、项目、页面、资产元数据、AI 会话和构建任务。
- 资源存储：local 模式下的 `backend-data` volume，或 S3 bucket。
- 构建产物：Backend 托管的 build artifacts。
- 密钥：`AI_SECRET_ENCRYPTION_KEY`、数据库密码、Redis 密码和对象存储凭证。

## AI 密钥

`AI_SECRET_ENCRYPTION_KEY` 用于加密用户模型凭证。恢复环境必须使用同一个值，否则历史凭证无法解密。

## local 存储

local 模式会把资源写入 Backend 数据 volume。备份数据库时，也要备份对应 volume 或挂载目录。

SQLite 轻量单容器模式下，`lite-data` volume 同时保存 SQLite 数据库、本地资源、截图、构建产物和 Runtime RSA 私钥。备份时应完整备份该 volume；只复制 `web_presentation.db` 会遗漏资源文件和密钥。容器运行中备份 SQLite 文件时，应同时复制 `web_presentation.db`、`web_presentation.db-wal` 和 `web_presentation.db-shm`，更推荐先停止容器或使用 volume 级快照。

## SQLite Demo 定时恢复

公开 Demo 可以使用 [`deploy/scripts/sqlite-demo-backup.sh`](../../../deploy/scripts/sqlite-demo-backup.sh) 保存一份完整 `lite-data` 基线，并使用 [`deploy/scripts/sqlite-demo-restore.sh`](../../../deploy/scripts/sqlite-demo-restore.sh) 定时恢复。两个脚本默认使用 `/opt/presentation/lite-data.tar.gz`，会从已有容器自动识别实际 volume 和镜像；操作期间停止 `platform-lite`，完成后重新启动并等待健康检查，无需写死 compose project 生成的 volume 名。

首次部署并整理好 Demo 初始数据后，在仓库根目录执行：

```bash
sudo sh ./deploy/scripts/sqlite-demo-backup.sh
```

手动验证恢复：

```bash
sudo sh ./deploy/scripts/sqlite-demo-restore.sh
```

确认无误后通过 `sudo crontab -e` 添加定时任务。以下示例每天北京时间 04:00 恢复；服务器不是北京时间时，应按服务器时区换算，或为 cron 配置对应时区：

```cron
0 4 * * * cd /opt/presentation && sh ./deploy/scripts/sqlite-demo-restore.sh >> /var/log/web-presentation-demo-restore.log 2>&1
```

可通过环境变量覆盖 `COMPOSE_FILE`、`COMPOSE_PROJECT_NAME`、`COMPOSE_SERVICE`、`DATA_MOUNT_PATH`、`BACKUP_FILE`、`LOCK_DIR` 和 `HEALTH_TIMEOUT_SECONDS`。如果部署时使用了 `docker compose -p <name>`，定时任务必须传入相同的 `COMPOSE_PROJECT_NAME`。基线文件包含数据库、用户上传内容以及加密密钥等敏感数据，应限制文件和目录权限。重置会造成短暂不可用，并永久删除基线之后产生的 Demo 数据；不要用于需要保留用户数据的正式环境。升级到包含新数据库迁移的镜像后，应验证兼容性并重新制作基线，避免旧版本镜像与新 schema 混用。

## S3 存储

S3 模式下，数据库保存元数据，文件保存在 bucket。恢复时需要确保 bucket、访问凭证和 `S3_PUBLIC_BASE_URL` 与部署配置一致。

## 恢复顺序

1. 恢复数据库；SQLite 轻量单容器模式恢复完整 `lite-data` volume。
2. 恢复资源和构建产物。
3. 恢复 `.env` 和密钥。
4. 启动与数据库 revision 匹配的平台镜像。
5. 验证登录、资源访问、预览、截图、构建和 AI 设置。
