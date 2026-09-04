<!-- 文件功能：面向个人与小团队自托管用户介绍 SQLite 单体版的日常维护、无损升级、数据备份还原与网络排障。 -->
# SQLite 单体版日常维护指南

本指南专为使用 `llmxpm/web-presentation:sqlite-lite` 单容器镜像的个人及小团队自托管用户编写。单体镜像已将控制面 Backend、渲染引擎 Runtime 和网关整合在一个容器中，日常维护非常轻量。

---

## 1. 容器无损升级

平台发布新版本后，推荐按照以下流程升级。

### 1.1 为什么升级不会丢失数据？
只要你在启动容器时挂载了命名数据卷（如 `lite-data`）或宿主机目录（如 `/app/backend/data`），所有业务数据（项目、页面、组件、主题、图片资源以及 SQLite 数据库文件）均持久化保存在宿主机上，不会因容器重建而丢失。

### 1.2 Docker Compose 升级流程

在你的 `compose.yaml` 所在目录下执行：

```bash
# 1. 拉取最新镜像
docker compose pull

# 2. 重建并重启服务（Docker 会自动保留原有数据卷挂载）
docker compose up -d

# 3. 检查运行状态与健康检查
docker compose ps
docker compose logs -f platform-lite
```

### 1.3 飞牛 fnOS / 群晖 Container Manager 升级流程
1. 进入容器管理套件中的“镜像”/“映像”列表，重新拉取 `llmxpm/web-presentation:sqlite-lite` 最新镜像。
2. 停止当前运行的 `web-presentation-lite` 容器。
3. 点击“更新”或“重置”容器（确保挂载目录保持原样），再启动容器。
4. 启动后通过浏览器访问验证。

---

## 2. 数据备份与恢复

生产或自建环境中最重要的事情是定期备份数据。

### 2.1 备份的核心对象
完整的备份必须包含两个部分：
1. **数据目录 / 数据卷**：包含 `web_presentation.db`（SQLite 主库及 WAL 临时文件）、用户上传的图片/字体/视频文件、渲染截图、构建静态产物以及 Runtime RSA 秘钥对；
2. **环境变量配置**：尤其是 `AI_SECRET_ENCRYPTION_KEY`（加密模型 API Key 的秘钥）。如果只备份了数据库而丢失了此秘钥，恢复后将无法解密先前保存的模型配置。

### 2.2 冷备份操作（推荐，最安全）

SQLite 在处于写入时直接复制数据库文件可能导致 WAL 日志未合并。推荐短暂停止容器后打包：

```bash
# 1. 短暂停止容器
docker compose stop platform-lite

# 2. 打包宿主机挂载目录（假设数据保存在 /data/web-presentation）
tar -czvf web-presentation-backup-$(date +%Y%m%d).tar.gz /data/web-presentation/data compose.yaml

# 3. 启动容器恢复服务
docker compose start platform-lite
```

如果使用的是 Docker 命名数据卷 `lite-data`，可通过辅助容器一键导出：

```bash
docker run --rm \
  -v lite-data:/data \
  -v $(pwd):/backup \
  alpine tar -czvf /backup/lite-data-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### 2.3 数据恢复流程

在全新机器或系统重装后恢复服务：

1. 准备好你的 `compose.yaml`，并确保 `AI_SECRET_ENCRYPTION_KEY` 与原环境完全一致；
2. 将备份的压缩包解压回对应的数据目录（或导入到新的 Docker volume 中）；
3. 确保数据目录的读写权限正常；
4. 启动容器：`docker compose up -d`；
5. 登录验证数据完整性与 AI 设置。

---

## 3. 局域网访问、反向代理与域名配置

许多个人或小团队部署在家用 NAS、内网服务器或轻量云主机上，常常遇到“内网能打开但页面无法预览”、“换了域名后报错”等网络配置问题。

### 3.1 三个关键环境变量的关系

在修改访问端口、绑定个人域名或配置 HTTPS 时，请确保以下三个变量保持联动：

| 环境变量 | 规则与示例 | 注意事项 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | 浏览器访问平台的完整公网/局域网根地址<br>如：`http://192.168.1.50:8080` 或 `https://ppt.yourdomain.com` | **结尾不要带斜杠**；用于平台生成公开链接和回调 |
| `RUNTIME_PUBLIC_BASE_URL` | 浏览器加载预览和资源的外部路径<br>如：`http://192.168.1.50:8080/runtime` 或 `https://ppt.yourdomain.com/runtime` | 单体版通常就是平台根地址加上 `/runtime` |
| `CORS_ORIGINS` | 合法的浏览器 Origin JSON 数组<br>如：`'["http://192.168.1.50:8080"]'` 或 `'["https://ppt.yourdomain.com"]'` | **必须为合法 JSON 数组字符串**；若来源不在列表中，前端 API 请求将被浏览器拦截 |

> **提示**：`RUNTIME_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL` 和 `RUNTIME_BACKEND_API_BASE_URL` 是容器内部回源地址，保持镜像内置的 `127.0.0.1` 即可，**绝对不要**改成公网域名或局域网 IP。

### 3.2 使用 Nginx / NPM 反向代理与 HTTPS

如果你在平台前端挂载了 Nginx Proxy Manager (NPM)、Caddy 或群晖反向代理并开启了 HTTPS：

1. 将 `BACKEND_PUBLIC_BASE_URL` 改为 `https://ppt.yourdomain.com`；
2. 将 `RUNTIME_PUBLIC_BASE_URL` 改为 `https://ppt.yourdomain.com/runtime`；
3. 将 `CORS_ORIGINS` 改为 `'["https://ppt.yourdomain.com"]'`；
4. 反向代理配置时，请确保传递标准代理头（`Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`），并支持 WebSocket 和 Server-Sent Events (SSE) 长连接（不要开启 Response Buffering 缓冲）。
