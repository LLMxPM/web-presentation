# AI 凭证加密密钥平滑迁移与轮换指南

本文档介绍平台 `AI_SECRET_ENCRYPTION_KEY` 的加密机制、凭证数据边界，以及在更换密钥时如何安全地对数据库中的供应商 API Key 进行平滑重密迁移，避免现有模型配置失效。

## 1. 核心机制与凭证边界

平台使用基于 Fernet 的对称加密算法对保存在数据库中的大模型 API Key（明文密钥）进行保护：

- **配置项**：`AI_SECRET_ENCRYPTION_KEY`（定义于后端配置中，通常在 `.env`、`deploy/.env` 或容器环境变量提供）。
- **密钥格式**：32 字节高强度随机数的 URL-safe Base64 编码（通常长度为 44 个字符并以 `=` 结尾）。
- **加密范围**：
  - 聊天供应商凭证表：`ai_chat_provider_configs.api_key_ciphertext`
  - 生图供应商凭证表：`ai_image_provider_configs.api_key_ciphertext`
- **安全检查机制**：
  后端在启动阶段（FastAPI lifespan）会通过 `_ensure_no_placeholder_secrets` 强制校验该配置。若配置值为空、格式不合法或使用了代码示例占位密钥（如 `vmgRweOsDpMtYVW7SSpceINYcXlUHFNndAby6vRv0iA=`），服务将主动拒绝启动并抛出 `SigningIdentityError`，防止弱密钥意外带入生产环境。

> [!WARNING]
> Fernet 对称加密要求加解密双方使用完全一致的密钥。若在数据库已有加密凭证的情况下直接在配置中修改 `AI_SECRET_ENCRYPTION_KEY`，解密将触发 `InvalidToken` 异常，接口抛出 `500 AI_LLM_API_KEY_INVALID`（大模型密钥解密失败），导致前端无法读取供应商凭证且所有关联 AI 对话和生图任务失败。

---

## 2. 适用场景

1. **从示例占位密钥迁移到生产正式密钥**：部署或升级后触发 `AI_SECRET_ENCRYPTION_KEY 禁止使用默认/示例占位值` 报错拦截，需更换为正式随机密钥并保留已有配置。
2. **定期安全轮换（Key Rotation）**：按照企业安全基线定期轮换加密主密钥。
3. **密钥泄露应急响应**：旧密钥疑似泄露，需在不中断业务配置的前提下全量重加密。

---

## 3. 本地开发环境操作流程

在本地源码开发环境下，直接使用 `uv` 运行平台维护脚本 `app.scripts.rotate_ai_secret_key`。脚本在**单一数据库事务**内读取旧凭证解密，使用新密钥重新加密并更新写回，任一环节失败全量回滚。

### 步骤一：演练模式检查（Dry Run）

在正式写入数据库前，建议通过 `--dry-run` 结合 `--generate-new-key` 进行解密和加密演练，确认现有数据库所有数据均可被旧密钥正常解密：

```powershell
uv run --project backend python -m app.scripts.rotate_ai_secret_key --generate-new-key --dry-run
```

若旧密钥并非当前 `.env` 中的值，可通过 `--old-key` 显式指定：

```powershell
uv run --project backend python -m app.scripts.rotate_ai_secret_key --old-key "<当前生效的旧密钥>" --generate-new-key --dry-run
```

终端将输出解密测试统计，例如：
```text
已自动生成新密钥: CLU4bID65xYXI3mIAicG8YsUaFN87yaO69kOaHzwPEA=
准备开始密钥轮换 (演练模式)...

==== 密钥轮换执行结果 ====
模式: DRY RUN (未写入数据库)
聊天供应商: 共 4 项，成功重密 4 项凭证
生图供应商: 共 2 项，成功重密 2 项凭证
```

### 步骤二：执行正式重加密

演练通过后，去除 `--dry-run` 标志执行真正重密写入（使用刚才生成的密钥或指定新密钥）：

```powershell
uv run --project backend python -m app.scripts.rotate_ai_secret_key --old-key "<旧密钥>" --new-key "<新密钥>"
```

或者直接生成并写入：

```powershell
uv run --project backend python -m app.scripts.rotate_ai_secret_key --generate-new-key
```

终端输出 `SUCCESS (已写入数据库)` 且无错误后，表示数据表中的密文已全部更新为新密钥加密形态。

### 步骤三：同步更新配置与重启

1. 将生成的新密钥更新至根目录 `.env` 文件：
   ```env
   AI_SECRET_ENCRYPTION_KEY=<你的新密钥>
   ```
2. 重启平台后端服务，确认启动日志中无 `SigningIdentityError` 报错。

---

## 4. 容器与 Docker Compose 部署操作流程

生产容器环境（Docker Compose / 容器化编排）下，宿主机通常不直接具备 Python 或数据库直连网络，且后端镜像工作目录固定为 `/app/backend`。

### 关键执行原则：容器存活与崩溃状态的区别

- **情况 A：服务正在运行（健康存活）**
  可直接使用 `docker compose exec <service> ...` 进入运行中容器执行脚本。
- **情况 B：服务因密钥校验失败而启动崩溃（CrashLoopBackOff / Exited 1）**
  此时容器已经退出，执行 `docker compose exec` 会报错 `container is not running`。
  必须使用 `docker compose run --rm <service> ...`。该命令会启动一个**与该服务共享完全相同网络、卷挂载和环境变量的临时容器**执行迁移脚本，执行完成后自动回收容器。

以下按不同 Compose 部署形态列出具体操作步骤：

### 形态 1：官方生产编排（`compose.prod.yml` / `compose.runtime-roles.yml`）

此形态下后端服务名称为 `backend`，环境变量统一由 `deploy/.env` 管理。

#### 1. 演练与重密
在项目根目录（或 `deploy` 目录）执行临时容器迁移：

```bash
# 1. 演练检查（自动生成新密钥并验证解密）
docker compose -f deploy/compose/compose.prod.yml run --rm backend \
  python -m app.scripts.rotate_ai_secret_key --old-key "<旧密钥>" --generate-new-key --dry-run

# 2. 正式重密写入
docker compose -f deploy/compose/compose.prod.yml run --rm backend \
  python -m app.scripts.rotate_ai_secret_key --old-key "<旧密钥>" --new-key "<刚才生成的新密钥>"
```

#### 2. 更新环境变量
编辑 `deploy/.env`，将新密钥填入：
```env
AI_SECRET_ENCRYPTION_KEY=<新密钥>
```

#### 3. 重启后端服务
```bash
docker compose -f deploy/compose/compose.prod.yml up -d backend
```

---

### 形态 2：SQLite Lite 单容器版（`compose.sqlite-lite.yml`）

此形态下服务名称为 `platform-lite`，数据库存储在名为 `lite-data` 的 Docker 卷中（`/app/backend/data/web_presentation.db`）。

> [!IMPORTANT]
> SQLite 为单进程单写锁模式。执行迁移前，请先确保原有 `platform-lite` 服务已停止，避免多个容器同时持有 SQLite 文件写锁：
> ```bash
> docker compose -f deploy/compose/compose.sqlite-lite.yml stop platform-lite
> ```

#### 1. 通过挂载卷的临时容器执行重密
```bash
# 1. 演练
docker compose -f deploy/compose/compose.sqlite-lite.yml run --rm platform-lite \
  python -m app.scripts.rotate_ai_secret_key --old-key "<旧密钥>" --generate-new-key --dry-run

# 2. 正式重密
docker compose -f deploy/compose/compose.sqlite-lite.yml run --rm platform-lite \
  python -m app.scripts.rotate_ai_secret_key --old-key "<旧密钥>" --new-key "<新密钥>"
```

#### 2. 更新 Compose 文件配置并启动
打开 `deploy/compose/compose.sqlite-lite.yml`，更新 `environment` 下的 `AI_SECRET_ENCRYPTION_KEY` 变量，然后重启服务：
```bash
docker compose -f deploy/compose/compose.sqlite-lite.yml up -d platform-lite
```

---

### 独立 PG/Redis 演练环境

若在单机测试或演练中使用独立启动的 PostgreSQL 容器（例如容器名 `wp-postgres-drill`）：

#### 1. 确保数据库运行并执行重密
```bash
# 若尚未启动独立演练数据库：
docker run -d --name wp-postgres-drill -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=web_presentation -p 5432:5432 postgres:16-alpine

# 使用 Python 脚本直连数据库执行重密：
DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/web_presentation" \
  uv run python -m app.scripts.rotate_ai_secret_key --old-key "<旧密钥>" --new-key "<新密钥>"
```

#### 2. 更新配置并启动生产平台服务
将新密钥更新至生产配置 `deploy/.env` 或对应的环境变量中，随后重启平台服务。

---

## 5. 多副本部署（Multi-Backend）特别约束

若部署了多 Backend 副本实例（如 `BACKEND_MULTI_INSTANCE=true`）：
1. **单一数据库操作**：重密脚本只需执行一次，数据库内的凭证即已全量更新。
2. **多副本密钥一致性**：必须在重启前将所有 Backend 容器实例、Pod 或配置中心的 `AI_SECRET_ENCRYPTION_KEY` **全部同步更新为同一个新密钥**。
3. **分批摘流与重启**：由于新旧密钥不互通，为避免请求打到持有旧密钥的容器出现解密失败，应在迁移完成后对 Backend 实例执行整批替换或滚动重启。

---

## 6. 故障排查与备选方案

### 1. 脚本执行报“凭证无法用旧密钥解密”

- **原因**：传入的 `--old-key` 与数据库中部分数据的加密密钥不匹配，通常发生在历史上手动切换过多次密钥或导入了外部数据库。
- **处理**：核对历史使用的配置备份，找出加密该批数据的旧密钥；若旧密钥已无法找回，只能放弃旧凭证（见下方清空重设）。

### 2. 旧密钥彻底丢失

若旧密钥完全遗失且无法解密历史凭证，可通过官方清空脚本重置 AI 模型配置（不影响用户、工作空间、项目、页面和图片资产）：

- **本地环境**：
  ```powershell
  uv run --project backend python -m app.scripts.reset_ai_model_configuration --confirm RESET_AI_CONFIGURATION
  ```
- **容器环境**：
  ```bash
  docker compose -f deploy/compose/compose.prod.yml run --rm backend \
    python -m app.scripts.reset_ai_model_configuration --confirm RESET_AI_CONFIGURATION
  ```

重置后配置新的 `AI_SECRET_ENCRYPTION_KEY` 并启动服务，随后在前端界面重新添加所需的供应商及 API Key。

---

## 7. 相关参考

- [AI 模型配置与目录](./ai-model-configuration.md)
- [部署环境变量](../../deployment/production/env-vars.md)
- [部署排障指南](../../deployment/operations/troubleshooting.md)
- [升级与回滚指南](../../deployment/operations/upgrade-rollback.md)
- [备份与恢复](../../deployment/operations/backup-restore.md)
