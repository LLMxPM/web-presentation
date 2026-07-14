# 自托管部署

本文面向想把 `web-presentation` 跑在自己机器或团队服务器上的开源用户。默认推荐先使用 SQLite 轻量单容器部署；它不需要准备 PostgreSQL 和 Redis，适合个人体验、小团队试用和低成本自托管。

完整生产运维细节见 [生产部署指南](../developer/deployment/README.md)。本文只保留开源用户完成部署和选型所需的最小信息。

## 选择部署方式

| 方式 | 适合场景 | 说明 |
| :--- | :--- | :--- |
| SQLite 轻量单容器 | 个人、小团队、快速自托管 | 一个容器内运行 Backend、Runtime 和 Gateway，数据写入 `lite-data` volume |
| 内置 PostgreSQL/Redis | 单机试部署、接近常规依赖形态 | Compose 同时启动平台、Runtime、PostgreSQL 和 Redis |
| 外部 PostgreSQL/Redis | 已有数据库和 Redis 基础设施 | Compose 只启动平台和 Runtime，依赖服务由外部提供 |
| production env 版 | 更正式的生产部署 | 使用 `deploy/.env` 管理变量，拆分迁移、Backend、Runtime 和 Gateway |

首次部署建议从 SQLite 轻量单容器开始。需要多实例、高并发写入、集中备份或接入现有数据库时，再切到 PostgreSQL/Redis 方案。四类模板的完整说明见 [Compose 部署说明](../developer/deployment/compose.md)。

## 前置条件

- 已安装 Docker Engine。
- 已安装 Docker Compose v2，可以运行 `docker compose version`。
- 部署机器可以拉取 `llmxpm/web-presentation:sqlite-lite` 镜像。
- 如果要绑定真实域名，需要提前准备反向代理和 HTTPS 证书。

直接使用 Docker Hub 发布镜像时，不需要初始化 `runtime/` 子模块，也不需要本地构建前端或后端。

## 快速部署

进入仓库的 `deploy/` 目录：

```bash
cd deploy
```

打开 `docker-compose.sqlite.yml`，至少修改以下变量：

| 变量 | 修改要求 |
| :--- | :--- |
| `DEFAULT_ADMIN_PASSWORD` | 改成正式管理员密码 |
| `AI_SECRET_ENCRYPTION_KEY` | 改成新生成的 Fernet 密钥，并长期保存 |
| `BACKEND_PUBLIC_BASE_URL` | 改成浏览器访问平台的地址，默认本机为 `http://127.0.0.1:8080` |
| `RUNTIME_PUBLIC_BASE_URL` | 同域部署通常为平台地址追加 `/runtime` |
| `CORS_ORIGINS` | JSON 数组字符串，包含浏览器访问平台的地址 |

如果你没有克隆仓库，也可以新建一个 `docker-compose.yml`，直接复制下面的简化配置使用。轻量镜像已经内置 SQLite、memory runtime、Runtime 内部地址和日志默认值，用户侧通常只需要配置访问地址、跨域来源、默认管理员密码和 AI 凭证加密密钥。

```yaml
services:
  platform-lite:
    image: llmxpm/web-presentation:sqlite-lite
    restart: unless-stopped
    environment:
      BACKEND_PUBLIC_BASE_URL: "http://127.0.0.1:8080"
      RUNTIME_PUBLIC_BASE_URL: "http://127.0.0.1:8080/runtime"
      CORS_ORIGINS: '["http://127.0.0.1:8080"]'
      DEFAULT_ADMIN_PASSWORD: "change-admin-password"
      AI_SECRET_ENCRYPTION_KEY: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    volumes:
      - lite-data:/app/backend/data
    ports:
      - "8080:80"

volumes:
  lite-data:
```

可以用 Python 生成 `AI_SECRET_ENCRYPTION_KEY`：

```bash
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

启动服务：

```bash
docker compose -f docker-compose.sqlite.yml config
docker compose -f docker-compose.sqlite.yml pull
docker compose -f docker-compose.sqlite.yml up -d
```

如果你使用上面的简化配置并保存为 `docker-compose.yml`，把命令中的 `-f docker-compose.sqlite.yml` 去掉即可。

默认访问地址是 `http://127.0.0.1:8080`。如果部署到服务器并开放给其他人访问，应把 compose 中的公网地址改成真实域名或服务器地址。

## 验证运行状态

查看容器状态：

```bash
docker compose -f docker-compose.sqlite.yml ps
```

检查入口健康状态：

```bash
curl -fsS http://127.0.0.1:8080/healthz
```

查看日志：

```bash
docker compose -f docker-compose.sqlite.yml logs -f platform-lite
```

Windows PowerShell 中如果 `curl` 被映射为 `Invoke-WebRequest`，可以改用 `curl.exe`。

## 数据保存与备份

SQLite 轻量单容器版使用 `lite-data` volume 保存主数据和本地文件，包括：

- SQLite 数据库。
- 上传的资源和字体。
- 页面截图。
- 构建产物。
- Runtime RSA 私钥。

备份时应完整备份 `lite-data` volume，不要只复制 SQLite 数据库文件。升级、迁移或更换服务器前，先确认该 volume 已备份。

不要在生产环境执行带 `-v` 的 `docker compose down -v`，否则会删除 compose 管理的数据卷。

## 升级建议

轻量部署升级前先备份 `lite-data`，然后在 `deploy/` 目录执行：

```bash
docker compose -f docker-compose.sqlite.yml pull
docker compose -f docker-compose.sqlite.yml up -d
```

如果需要严格回滚，建议把 compose 中的镜像标签固定到明确版本，而不是一直使用 `sqlite-lite`。数据库迁移和回滚注意事项见 [升级与回滚](../developer/deployment/upgrade-rollback.md)。

## 什么时候切到生产部署

出现以下情况时，建议阅读 [生产部署指南](../developer/deployment/README.md)，并切到 PostgreSQL/Redis 或 production env 版：

- 多人长期使用，需要稳定备份、升级和回滚流程。
- 需要接入对象存储保存资源和构建产物。
- 需要公网 HTTPS、统一域名、网关或云负载均衡。
- 需要使用外部 PostgreSQL、Redis、日志采集和监控系统。
- 需要更细的部署排障、数据库迁移和版本锁定策略。
