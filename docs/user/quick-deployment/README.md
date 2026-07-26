# 快速部署

本章节只覆盖“尽快跑起来”的 SQLite 单体版，适合体验、个人使用和小团队使用。三种方式使用同一个镜像：`llmxpm/web-presentation:sqlite-lite`。如果需要 HTTPS、外部数据库、对象存储、备份策略或多实例，请直接阅读[生产部署指南](../../developer/deployment/README.md)。

## 选择部署方式

| 方式 | 适合场景 | 指导 |
| :--- | :--- | :--- |
| Docker 命令行 | Linux、Windows、macOS 或云服务器 | [Docker 快速部署](./docker.md) |
| 飞牛 fnOS | 家庭服务器、软路由或国产 NAS | [飞牛 fnOS 快速部署](./fnos.md) |
| 群晖 DSM | 群晖 NAS | [群晖 Container Manager 快速部署](./synology.md) |

三种方式都需要：

- 可以访问 Docker Hub，并能拉取 `llmxpm/web-presentation:sqlite-lite`。
- 将 `DEFAULT_ADMIN_PASSWORD` 修改为正式管理员密码。
- 生成并长期保存 `AI_SECRET_ENCRYPTION_KEY`。它用于加密模型凭证，丢失或更换后已保存的凭证无法解密。
- 确保主机端口 `8080` 未被占用；如果修改端口映射，还要同步修改公开地址和 `CORS_ORIGINS`。

## 通用配置

使用仓库中的 [`deploy/docker-compose.sqlite.yml`](../../../deploy/docker-compose.sqlite.yml)。至少修改：

| 配置 | 示例 | 作用 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | `http://192.168.1.20:8080` | 浏览器访问平台的外部入口，系统用它生成平台链接 |
| `RUNTIME_PUBLIC_BASE_URL` | `http://192.168.1.20:8080/runtime` | 浏览器访问 Runtime 预览和资源的外部路径 |
| `CORS_ORIGINS` | `'["http://192.168.1.20:8080"]'` | 允许访问平台的浏览器来源，必须填写平台外部入口 |
| `DEFAULT_ADMIN_PASSWORD` | 自定义强密码 | 首次登录的默认管理员密码，登录后应立即修改 |
| `AI_SECRET_ENCRYPTION_KEY` | 由随机数生成的 Fernet 密钥 | 加密保存模型 API Key，必须长期备份且不能随意更换 |

### 公网地址与容器内地址

下面的地址不是都填写成浏览器访问地址。SQLite 单体版把 Backend、Runtime 和 Gateway 放在同一个容器中，用户只需要填写 3 个外部访问相关变量；其余内部变量由镜像默认值提供。

| 变量 | 谁访问谁 | SQLite 单体版配置 | 是否填写外部访问地址 |
| :--- | :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | 浏览器访问平台入口 | `http://主机地址:8080` | 是 |
| `RUNTIME_BASE_URL` | Backend 访问同容器内 Runtime | `http://127.0.0.1:7373` | 否 |
| `RUNTIME_PUBLIC_BASE_URL` | 浏览器访问 Runtime 的公开路径 | `http://主机地址:8080/runtime` | 是 |
| `RUNTIME_PREVIEW_JWKS_URL` | Runtime 访问 Backend 的签名公钥 | `http://127.0.0.1:8000/.well-known/jwks.json` | 否 |
| `RUNTIME_BACKEND_API_BASE_URL` | Runtime 回源 Backend API | `http://127.0.0.1:8000` | 否 |

其中，`8080` 是宿主机对外映射到容器 `80` 的端口；`8000` 是容器内 Backend 端口，`7373` 是容器内 Runtime 端口，单体版不需要把这两个端口暴露给局域网或公网。Gateway 会把浏览器访问的 `/api`、`/public`、`/preview` 等路径转给 Backend，把 `/runtime/` 路径转给 Runtime。

因此，部署到 NAS 或服务器时通常只需要把以下三个值中的主机地址和外部端口改成实际值：

```text
BACKEND_PUBLIC_BASE_URL=http://192.168.1.20:8080
RUNTIME_PUBLIC_BASE_URL=http://192.168.1.20:8080/runtime
CORS_ORIGINS=["http://192.168.1.20:8080"]
```

如果把端口映射改为 `18080:80`，上述三个值都要改为 `18080`；`RUNTIME_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL` 和 `RUNTIME_BACKEND_API_BASE_URL` 仍保持镜像内置的 `127.0.0.1` 地址，不需要填写到用户 Compose 或 `docker run` 命令中。只有改成 Backend、Runtime 分开容器或使用独立 Runtime 域名时，才需要按[详细部署指南](../../developer/deployment/README.md)重新配置内部地址和路径。

生成密钥：

```bash
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

## 部署后检查

浏览器访问 `http://主机地址:8080`，然后检查：

```bash
curl -fsS http://127.0.0.1:8080/healthz
docker compose -f docker-compose.sqlite.yml ps
```

SQLite 数据库、上传资源、截图、构建产物和 Runtime RSA 私钥都保存在 `lite-data` 数据卷或 `/app/backend/data` 挂载目录中。备份时必须完整备份该数据卷或目录，不要只复制 SQLite 文件；不要执行 `docker compose down -v`。

快速部署适合体验和小规模自托管。需要 HTTPS、外部 PostgreSQL/Redis、对象存储、集中日志、迁移、升级回滚或多实例部署时，请阅读[开发文档中的详细部署指南](../../developer/deployment/README.md)。
