# Docker 快速部署

本页提供 Docker Compose 和单容器 `docker run` 两种部署方式。`sqlite-lite` 镜像采用单容器架构，内置 Backend、Editor、Runtime、Renderer（含 Chromium 浏览器）与 Nginx Gateway，**无需任何必填环境变量，无需 secret 密钥文件**，开箱即用。

## 1. 一键命令行启动（零必填变量）

如果你想在本机或单机上快速体验，只需创建数据卷并运行单容器命令（0 环境变量）：

```bash
# 1. 创建持久化数据卷（存储数据库、上传资产、自动生成的加密密钥与截图）
docker volume create web-presentation-lite-data

# 2. 拉取统一镜像
docker pull llmxpm/web-presentation:sqlite-lite

# 3. 启动单容器服务（无需配置 -e 环境变量，开箱即用）
docker run -d \
  --name web-presentation \
  --restart unless-stopped \
  -p 8080:80 \
  -v web-presentation-lite-data:/app/backend/data \
  llmxpm/web-presentation:sqlite-lite
```

### 查看初始管理员密码

首次建库启动时，系统会自动生成 16 位高强度随机管理员密码并输出在日志中：

```bash
docker logs web-presentation
```

在终端输出中找到如下信息：

```text
====================================================================
[Lite 首启提示] 已为平台管理员账号 (admin) 自动生成初始随机密码：
       <一串随机字符>
请保存此密码，并在登录后尽快通过系统设置修改管理员口令。
====================================================================
```

浏览器打开 `http://127.0.0.1:8080`，使用账号 `admin` 和该随机密码即可登录。登录后建议进入右上角「账户设置」或「系统设置」修改密码。

## 2. Docker Compose 编排部署（推荐局域网/私有云）

若部署在家庭 NAS、局域网服务器或有固定 IP / 域名的环境，推荐使用 Docker Compose 声明外部访问地址。

在任意空目录下创建 `compose.yaml`：

```yaml
services:
  platform-lite:
    image: llmxpm/web-presentation:sqlite-lite
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - lite-data:/app/backend/data
    environment:
      # 外部访问地址（局域网请将 127.0.0.1 替换为实际主机 IP，如 192.168.1.20）
      BACKEND_PUBLIC_BASE_URL: "http://127.0.0.1:8080"
      RUNTIME_PUBLIC_BASE_URL: "http://127.0.0.1:8080/runtime"
      CORS_ORIGINS: '["http://127.0.0.1:8080"]'
      # 可选：显式指定管理员密码（留空则首启自动生成随机密码）
      # DEFAULT_ADMIN_PASSWORD: "MyCustomStrongPassword123"

volumes:
  lite-data:
```

### 启动与健康检查

```bash
# 启动容器
docker compose up -d

# 查看容器运行状态
docker compose ps

# 检查健康检查接口
curl -fsS http://127.0.0.1:8080/healthz

# 查看实时日志（获取自动生成的管理员密码）
docker compose logs -f platform-lite
```

## 3. 环境变量说明（全部为可选配置）

| 环境变量 | 默认值 | 作用说明 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | `http://127.0.0.1:8080` | 浏览器外部访问平台的基础 URL。若通过局域网其它电脑或域名访问，填入对应实际地址。 |
| `RUNTIME_PUBLIC_BASE_URL` | `<BACKEND_PUBLIC_BASE_URL>/runtime` | 浏览器外部访问 Runtime 运行时的入口 URL。 |
| `CORS_ORIGINS` | `'["http://127.0.0.1:8080"]'` | 允许的跨域来源 JSON 数组，需与浏览器访问地址保持一致。 |
| `DEFAULT_ADMIN_PASSWORD` | *(未配置时首启自动生成)* | 初始管理员账号密码。若设置了自定义密码，首次建库时将直接采用。 |
| `AI_SECRET_ENCRYPTION_KEY` | *(未配置时自动生成落盘)* | 大模型凭证对称加密密钥（Fernet）。未配置时系统首次启动自动生成 32 字节密钥并持久化保存至 `/app/backend/data/ai_secret.key`，用户无需手动生成或配置。 |

> **提示**：容器内子进程之间的通信地址（如 `RUNTIME_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL` 等）由镜像自动维护在回环网络 `127.0.0.1`，**切勿手动覆盖为外部地址**。

## 4. 数据持久化与备份

SQLite 数据库、上传素材、截图产物、自动生成的加密密钥和 Runtime RSA 密钥均持久化保存在挂载的 `lite-data` 数据卷内（对应容器内 `/app/backend/data`）。

- **日常升级**：直接执行 `docker compose pull && docker compose up -d` 即可无损升级镜像。
- **备份与迁移**：只需备份挂载的数据卷或宿主机对应的数据目录；不要执行 `docker compose down -v`。
- 日常运维、数据备份恢复与反代配置请参考 [SQLite 单体版日常维护指南](./maintenance.md)；多副本高可用或 PostgreSQL 集群部署请阅读[生产部署指南](../../developer/deployment/README.md)。
