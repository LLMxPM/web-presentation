# 快速部署

本章节只覆盖“尽快跑起来”的 SQLite 单体版，适合体验、个人使用和小团队使用。三种部署方式（Docker 命令行、飞牛 fnOS、群晖 DSM）使用同一个统一镜像：`llmxpm/web-presentation:sqlite-lite`。如果需要 HTTPS、外部数据库、对象存储、备份策略或多实例，请直接阅读[生产部署指南](../../developer/deployment/README.md)。

**形态说明（单容器即全部能力）**：`sqlite-lite` 是**单容器**部署，Backend、Runtime、Gateway 与页面截图 Chromium 浏览器均打包在同一个镜像内。你**不需要**准备任何 secret 密钥文件，**不需要**再启动第二个 Renderer 容器，也**不需要**配置复杂的必填环境变量——群晖 Container Manager、飞牛 fnOS 等图形界面路径也只需要创建一个容器即可完整运行。

## 核心特性：零必填变量、零密钥文件

- **0 必填环境变量**：直接启动容器即可运行；默认管理端口为 `8080:80`。
- **凭据与密钥自动生成**：
  - **AI 凭证加密密钥**：首次启动时自动生成 32 字节 Fernet 密钥并持久化保存在数据卷内（`/app/backend/data/ai_secret.key`），容器重启不丢失，无需手动生成与保管。
  - **管理员初始密码**：若未显式指定 `DEFAULT_ADMIN_PASSWORD`，系统首次启动会自动生成高强度随机密码并打印在容器启动日志中，登录后可点击右上角头像「修改密码」随时修改。
  - **内部通信凭证**：各子进程间共享密钥自动就地派生，杜绝占位符泄露。
- **内置截图引擎**：已发布镜像内置轻量 Chromium 与渲染服务，页面缩略图、幻灯片快照开箱即用。

## 选择部署方式

| 方式 | 适合场景 | 指导 |
| :--- | :--- | :--- |
| Docker 命令行 | Linux、Windows、macOS 或云服务器 | [Docker 快速部署](./docker.md) |
| 飞牛 fnOS | 家庭服务器、软路由或国产 NAS | [飞牛 fnOS 快速部署](./fnos.md) |
| 群晖 DSM | 群晖 NAS | [群晖 Container Manager 快速部署](./synology.md) |
| 日常运维与升级 | 升级容器、备份还原数据、反代网络排障 | [SQLite 单体版日常维护指南](./maintenance.md) |

## 一键极简启动示例（零变量）

只需一行命令即可在本机启动完整服务：

```bash
docker run -d \
  --name web-presentation \
  --restart unless-stopped \
  -p 8080:80 \
  -v lite-data:/app/backend/data \
  llmxpm/web-presentation:sqlite-lite
```

启动后查看初始管理员密码：

```bash
docker logs web-presentation
```

在日志中即可看到形如 `[Lite 首启提示] 已为平台管理员账号 (admin) 自动生成初始随机密码` 的提示，使用该密码在浏览器访问 `http://127.0.0.1:8080` 登录。

## 可选外部访问配置

使用仓库中的编排模板 [`deploy/compose/compose.sqlite-lite.yml`](../../../deploy/compose/compose.sqlite-lite.yml)。若在局域网 NAS、私有云或自定义域名下访问，可按需补充以下外部入口环境变量：

| 配置 | 默认值 / 示例 | 作用 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | `http://127.0.0.1:8080`（局域网示例：`http://192.168.1.20:8080`） | 浏览器访问平台的外部入口，系统用它生成平台链接 |
| `RUNTIME_PUBLIC_BASE_URL` | `http://127.0.0.1:8080/runtime`（局域网示例：`http://192.168.1.20:8080/runtime`） | 浏览器访问 Runtime 预览和资源的外部路径 |
| `CORS_ORIGINS` | `'["http://127.0.0.1:8080"]'`（局域网示例：`'["http://192.168.1.20:8080"]'`） | 允许访问平台的浏览器来源，必须填写平台外部入口 |
| `DEFAULT_ADMIN_PASSWORD` | 留空（自动生成随机密码）或自定义强密码 | 首次建库时的管理员初始口令 |

### 容器内地址与端口映射说明

SQLite 单体版将 Backend（8000）、Runtime（7373）、Renderer（7400）与 Gateway（80）运行在同一容器内，外部只需将容器的 `80` 端口映射为主机端口（如 `8080:80`）。所有容器内部通信（`RUNTIME_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL` 等）默认均绑定回环地址 `127.0.0.1`，**切勿将内部地址改为外部主机或局域网 IP**。

若修改宿主机映射端口（如改为 `18080:80`），且指定了外部访问地址，请将 `BACKEND_PUBLIC_BASE_URL`、`RUNTIME_PUBLIC_BASE_URL` 和 `CORS_ORIGINS` 中的端口同步修改为 `18080`。

## 部署后检查

```bash
curl -fsS http://127.0.0.1:8080/healthz
```

SQLite 数据库、上传资源、截图产物和持久化密钥均保存在挂载的 `lite-data` 数据卷（容器内 `/app/backend/data`）中。备份与迁移时只需完整备份该数据卷或主机对应目录即可；不要执行 `docker compose down -v`。

## 适用规模与故障域

| 项 | 说明 |
| :--- | :--- |
| 推荐规模 | **5–10 人小团队**，预览并发**约 3**，常规演示文稿工作区（非海量资产库） |
| 承诺级别 | **容量验收前这是目标规模，不是 SLA / 硬承诺**；实际能力以你的主机配置与使用方式为准 |
| 故障域 | Backend、Runtime、Gateway 与渲染合并故障域；**容器或服务重启会丢失预览/构建临时运行态**（进行中的 AI 长任务也可能中断且不自动续跑），**业务数据不丢**（均在数据卷内） |

快速部署适合体验和小规模自托管。需要 HTTPS、外部 PostgreSQL/Redis、对象存储、集中日志、迁移、升级回滚或多实例部署时，请阅读[开发文档中的详细部署指南](../../developer/deployment/README.md)。
