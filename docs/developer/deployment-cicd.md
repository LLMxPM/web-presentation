<!-- 文件功能：说明平台镜像构建、Docker Hub 发布、Runtime 子项目镜像耦合和生产 compose 部署方式。 -->
# CI/CD 与容器部署说明

## 发布边界

根仓只发布一个平台镜像：`llmxpm/web-presentation`。该镜像同时包含 Backend 代码、Editor 静态资源、Nginx 配置和 Backend 运行所需的 Runtime Kit manifest。

`runtime/` 仍是独立项目 `web-runtime-vue` 的子模块接入目录。根仓不会构建 Runtime 镜像，只会在平台 Release 前校验当前子模块 SHA 对应的 Runtime 镜像已存在：

```bash
docker buildx imagetools inspect docker.io/llmxpm/web-runtime-vue:sha-<runtime_sha_short>
```

`web-runtime-vue` 子仓库自己的 Docker Release 会发布 `<release_tag>`、`sha-<runtime_sha_short>`，稳定 Release 还会发布 `latest`。平台仓库更新 `runtime` 子模块指针前，应先让对应 Runtime 提交完成子仓库 Release。

## GitHub Actions

- PR：`.github/workflows/platform-test.yml` 执行快速质量门禁，包括 Backend unit/api、Editor、根仓 contracts；当 `runtime` 子模块或 `.gitmodules` 变化时，额外执行 Runtime 委托校验。
- 全量测试：`.github/workflows/platform-test.yml` 仅在 `main` push、每周一 03:00（Asia/Shanghai）定时任务或手动触发且 `full_tests=true` 时执行；全量会在快速门禁基础上补充 Backend integration、Runtime 委托校验、e2e smoke 和平台镜像 build smoke。平台镜像 build smoke 只构建，不推送。
- Release：`.github/workflows/platform-release.yml` 在 GitHub Release `published` 后执行完整质量门禁；Backend、Editor 和 contracts 通过后再执行 e2e smoke 与 Runtime 镜像存在性校验，最后推送 Docker Hub。
- Docker Hub 配置：
  - `vars.DOCKER_USERNAME`
  - `secrets.DOCKER_PASSWORD`

稳定 Release 会推送：

```text
docker.io/llmxpm/web-presentation:<release_tag>
docker.io/llmxpm/web-presentation:latest
```

Pre-release 只推送版本标签，不移动 `latest`。

## 生产 Compose

生产部署不在目标机器构建镜像，只拉取 CI/CD 已发布的两个业务镜像。镜像仓库固定为：

- `llmxpm/web-presentation:latest`
- `llmxpm/web-runtime-vue:latest`

部署模板集中在 `deploy/` 目录：

- `deploy/docker-compose.yml`：外部 PostgreSQL/Redis 简化版，环境变量直接写在 compose 内。
- `deploy/docker-compose.with-deps.yml`：内置 PostgreSQL/Redis 简化版，随应用一起启动 PostgreSQL 与 Redis，环境变量直接写在 compose 内。
- `deploy/docker-compose.production.yml`：production env 版，拆分迁移、Backend、Runtime 与 Gateway，并通过 `env_file: .env` 读取环境变量。
- `deploy/.env.example`：仅供 production env 版复制为 `deploy/.env` 使用。

内置依赖简化版启动方式：

```bash
cd deploy
docker compose -f docker-compose.with-deps.yml config
docker compose -f docker-compose.with-deps.yml pull
docker compose -f docker-compose.with-deps.yml up -d
```

外部依赖简化版使用默认 `docker-compose.yml`；production env 版需要先复制 `deploy/.env.example` 为 `deploy/.env`，再将命令中的 compose 文件改为 `docker-compose.production.yml`。完整部署、升级、回滚和运维检查流程见 [生产部署指南](./deployment-guide.md)。

正式部署前必须替换数据库密码、默认管理员密码和 `AI_SECRET_ENCRYPTION_KEY`。`AI_SECRET_ENCRYPTION_KEY` 必须是 Fernet 密钥，即 32 字节随机值的 URL-safe base64 编码，通常长度为 44 个字符并以 `=` 结尾；可用 `python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` 生成。部署后应长期保存，随意更换会导致已有用户模型凭证密文无法解密。

AI 会话历史清理相关变量也应随部署模板保留：`AI_SESSION_RETENTION_DAYS=15`、`AI_SESSION_CLEANUP_INTERVAL_SECONDS=21600`、`AI_SESSION_CLEANUP_BATCH_SIZE=500`。该清理只删除超过保留期未更新的整条 Agno session；如 PostgreSQL JSONB/TOAST 已膨胀，普通删除后仍需运维窗口手动执行 `VACUUM FULL` 或 `pg_repack` 才能回收物理磁盘。

两个简化版中，同一个平台镜像只启动一个长期运行的 `platform` 容器。该容器入口脚本会先执行 `alembic upgrade head`，再同时启动：

- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
- `nginx -g 'daemon off;'`

production env 版中，同一个平台镜像会拆分为三个容器：

- `backend-migrate`：执行 `alembic upgrade head`
- `backend`：执行 `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
- `gateway`：执行 `nginx -g 'daemon off;'`，托管 Editor 并代理 Backend/Runtime

compose 默认跟随 `latest`。如果需要严格锁定 Runtime 与平台版本，应同时把对应 compose 文件中的平台 image 改为 `llmxpm/web-presentation:<release_tag>`，把 Runtime image 改为 `llmxpm/web-runtime-vue:<release_tag>` 或子项目发布的 `sha-<runtime_sha_short>` 标签。不要只回滚平台镜像或只回滚 Runtime 镜像；数据库迁移一旦前进，平台镜像必须仍然包含数据库 `alembic_version` 指向的 revision 文件。

## 关键访问关系

- 浏览器访问简化版的 `platform:80`，或 production env 版的 `gateway:80`。
- 平台 Nginx 代理 `/api`、`/public`、`/build-artifacts`、`/preview`、`/media` 到 `backend:8000`。
- 平台 Nginx 代理 `/runtime/` 到 `runtime:7373`，并保留 `/runtime/` 前缀。
- Backend 通过 `RUNTIME_BASE_URL=http://runtime:7373` 访问 Runtime 内网服务。
- Runtime 通过 `RUNTIME_BACKEND_API_BASE_URL=http://backend:8000` 回源 Backend 内部接口。
- Runtime 通过 `RUNTIME_PREVIEW_JWKS_URL=http://backend:8000/.well-known/jwks.json` 校验 Backend 签发的预览与构建令牌。
