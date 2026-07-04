# Compose 部署说明

`deploy/` 提供三类部署模板，覆盖快速试部署、外部依赖部署和 production env 版部署。

## 模板

| 文件 | 场景 | 特点 |
| :--- | :--- | :--- |
| `deploy/docker-compose.with-deps.yml` | 单机试部署 | 内置 PostgreSQL、Redis、platform 和 runtime |
| `deploy/docker-compose.yml` | 外部依赖简化版 | 只启动 platform 和 runtime，数据库与 Redis 使用外部服务 |
| `deploy/docker-compose.production.yml` | 生产 env 版 | 拆分迁移、Backend、Runtime 和 Gateway，通过 `deploy/.env` 管理变量 |

## 试部署

```bash
cd deploy
docker compose -f docker-compose.with-deps.yml pull
docker compose -f docker-compose.with-deps.yml up -d
```

默认访问 `http://127.0.0.1:8080`。上线前必须修改 compose 顶部注释要求的密码、访问地址和 `AI_SECRET_ENCRYPTION_KEY`。

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
