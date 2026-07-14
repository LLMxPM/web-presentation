# Compose 部署说明

`deploy/` 提供四类部署模板，覆盖 SQLite 轻量单容器、快速试部署、外部依赖部署和 production env 版部署。

## 模板

| 文件 | 场景 | 特点 |
| :--- | :--- | :--- |
| `deploy/docker-compose.sqlite.yml` | 个人/小团队轻量部署 | 单容器内置 Backend、Editor、Runtime 和 Gateway，使用 SQLite 文件与 memory runtime |
| `deploy/docker-compose.with-deps.yml` | 单机试部署 | 内置 PostgreSQL、Redis、platform 和 runtime |
| `deploy/docker-compose.yml` | 外部依赖简化版 | 只启动 platform 和 runtime，数据库与 Redis 使用外部服务 |
| `deploy/docker-compose.production.yml` | 生产 env 版 | 拆分迁移、Backend、Runtime 和 Gateway，通过 `deploy/.env` 管理变量 |

## SQLite 轻量单容器

```bash
cd deploy
docker compose -f docker-compose.sqlite.yml config
docker compose -f docker-compose.sqlite.yml pull
docker compose -f docker-compose.sqlite.yml up -d
```

默认拉取 `llmxpm/web-presentation:sqlite-lite`，访问 `http://127.0.0.1:8080`。该模式不启动 PostgreSQL 和 Redis，`DATABASE_URL` 指向 `/app/backend/data/web_presentation.db`，`REDIS_URL` 使用 `memory://lite`。`lite-data` volume 同时保存 SQLite 数据库、本地资源、截图、构建产物和 Runtime RSA 私钥。

需要从源码验证轻量镜像时，必须先初始化 `runtime/` 子模块；`Dockerfile.lite` 会把当前子模块源码和依赖一起打进单容器镜像，而不是拉取 `web-runtime-vue` 镜像作为基础层。

```bash
git submodule update --init --recursive runtime
docker build -f Dockerfile.lite -t llmxpm/web-presentation:sqlite-lite .
```

轻量模式只支持单容器、单 Backend worker、单 Runtime server，不适合多副本或高并发写入。容器重启后短生命周期预览链接、内存锁和内存构建状态会失效，但用户、工作空间、项目、页面、资源和 AI 会话等主数据会保留在 SQLite 文件中。

## 试部署

```bash
cd deploy
docker compose -f docker-compose.with-deps.yml pull
docker compose -f docker-compose.with-deps.yml up -d
```

默认访问 `http://127.0.0.1:8080`。上线前必须修改 compose 顶部注释要求的密码、访问地址和 `AI_SECRET_ENCRYPTION_KEY`。

内置 Redis 默认关闭 AOF，减少低配单机上的持续磁盘写入。该 Redis 只承载短生命周期运行态，不保存平台主数据。

## production env 版

```bash
cp deploy/.env.example deploy/.env
cd deploy
docker compose -f docker-compose.production.yml config
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
```

production env 版适合把环境变量集中放在 `deploy/.env` 中维护。外部 PostgreSQL 和 Redis 需要提前准备。

## 访问关系

浏览器访问平台 Gateway。Gateway 代理 `/api`、`/public`、`/build-artifacts`、`/preview`、`/media` 到 Backend，并代理 `/runtime/` 到 Runtime。
