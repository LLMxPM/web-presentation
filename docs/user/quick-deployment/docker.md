# Docker

本页提供 Docker Compose 和单容器 `docker run` 两种方式。用户通常只需要配置 5 个变量；Runtime、队列、日志和容器内回源地址使用 SQLite 单体镜像默认值。

## 1. Docker Compose 部署

在任意空目录创建 `compose.yaml`，复制下面的完整内容。正式部署前必须修改 5 个变量：

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

变量说明：

| 变量 | 是否必须修改 | 含义 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | 是 | 浏览器访问平台的外部地址，例如 `http://192.168.1.20:8080` |
| `RUNTIME_PUBLIC_BASE_URL` | 是 | 浏览器访问 Runtime 的外部路径，通常为平台地址加 `/runtime` |
| `CORS_ORIGINS` | 是 | JSON 数组，填写浏览器访问平台的同一个外部地址 |
| `DEFAULT_ADMIN_PASSWORD` | 是 | 首次登录使用的默认管理员密码，部署后应立即修改 |
| `AI_SECRET_ENCRYPTION_KEY` | 是 | 加密模型 API Key 的 Fernet 密钥，生成后必须长期保存，不能随意更换 |

生成 `AI_SECRET_ENCRYPTION_KEY`：

```bash
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

如果宿主机 8080 端口被占用，可将端口映射改为 `18080:80`，并把上述 3 个地址中的端口同步改为 `18080`。

启动和检查：

```bash
docker compose -f compose.yaml config
docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
curl -fsS http://127.0.0.1:8080/healthz
docker compose -f compose.yaml logs -f platform-lite
```

## 2. `docker run` 部署

下面的命令同样只配置必要变量。请替换尖括号中的内容；`<主机地址>` 应是浏览器实际访问的平台地址。

```bash
docker volume create web-presentation-lite-data
docker pull llmxpm/web-presentation:sqlite-lite
docker run -d \
  --name web-presentation-lite \
  --restart unless-stopped \
  -p 8080:80 \
  -v web-presentation-lite-data:/app/backend/data \
  -e BACKEND_PUBLIC_BASE_URL="http://<主机地址>:8080" \
  -e RUNTIME_PUBLIC_BASE_URL="http://<主机地址>:8080/runtime" \
  -e CORS_ORIGINS='["http://<主机地址>:8080"]' \
  -e DEFAULT_ADMIN_PASSWORD="<管理员密码>" \
  -e AI_SECRET_ENCRYPTION_KEY="<Fernet密钥>" \
  llmxpm/web-presentation:sqlite-lite
```

检查容器：

```bash
docker ps
curl -fsS http://127.0.0.1:8080/healthz
docker logs -f web-presentation-lite
```

## 3. 数据与高级配置

SQLite 数据库、资源、截图、构建产物和 Runtime RSA 私钥保存在 `lite-data` 或 `web-presentation-lite-data` 中。升级前先备份数据卷；不要使用 `docker compose down -v`，也不要删除该数据卷。

Runtime 内部回源地址、Runtime 资源路径、队列并发、日志、HTTPS、外部数据库和对象存储等高级变量已由镜像或部署模板提供默认值。需要调整这些配置时，请阅读[开发文档中的详细部署指南](../../developer/deployment/README.md)，不要在用户快速部署文件中自行复制整套高级变量。
