# 群晖

本页按群晖 DSM 的 Container Manager 图形界面编写，不要求 SSH 或命令行。不同 DSM 版本的按钮名称可能略有差异。

## 1. 拉取镜像

1. 在套件中心安装并打开 **Container Manager**。
2. 进入“映像”或“注册表”，搜索 `llmxpm/web-presentation`。
3. 选择标签 `sqlite-lite`，点击“下载”。
4. 等待镜像出现在本地映像列表。

> 截图占位：Container Manager 注册表搜索并下载 `llmxpm/web-presentation:sqlite-lite` 的页面。

## 2. 创建容器

1. 在“映像”中选中 `llmxpm/web-presentation:sqlite-lite`，点击“启动”。
2. 容器名称填写 `web-presentation-lite`。
3. 勾选“启用自动重新启动”或选择等效的重启策略。
4. 进入高级设置，依次配置端口、存储空间和环境变量。

> 截图占位：Container Manager 从映像启动容器、填写名称和重启策略的页面。

## 3. 配置端口和存储空间

### 端口设置

在“端口设置”中新增：

| 本地端口 | 容器端口 | 类型 |
| :--- | :--- | :--- |
| `8080` | `80` | TCP |

如果群晖 8080 端口已被占用，可以把本地端口改成 `18080`，并同步修改环境变量中的访问地址。

### 存储空间设置

在 File Station 中创建共享文件夹 `docker` 和子目录 `web-presentation/data`，然后在“存储空间设置”新增：

| 本地文件夹 | 挂载路径 | 读写 |
| :--- | :--- | :--- |
| `/docker/web-presentation/data` | `/app/backend/data` | 读写 |

整个目录必须挂载为读写；不要只挂载 `web_presentation.db`。

> 截图占位：Container Manager 端口设置和存储空间设置页面。

## 4. 配置环境变量

在“环境”或“环境变量”页面新增或修改：

| 变量名 | 示例值 | 作用 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | `http://192.168.1.30:8080` | 浏览器访问平台的外部入口，系统用它生成平台链接 |
| `RUNTIME_PUBLIC_BASE_URL` | `http://192.168.1.30:8080/runtime` | 浏览器访问 Runtime 预览和资源的外部路径 |
| `CORS_ORIGINS` | `["http://192.168.1.30:8080"]` | 允许访问平台的浏览器来源，必须填写平台外部入口 |
| `DEFAULT_ADMIN_PASSWORD` | 自定义强密码 | 首次登录的默认管理员密码，登录后应立即修改 |
| `AI_SECRET_ENCRYPTION_KEY` | 生成的 Fernet 密钥 | 加密保存模型 API Key，必须长期备份且不能随意更换 |

其余参数使用镜像默认值即可。

### 生成 AI 加密密钥

在自己的电脑上生成密钥，不要使用示例值。电脑已安装 Python 时，在 PowerShell、macOS 或 Linux 终端执行：

```bash
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

复制命令输出的整行内容，粘贴到 Container Manager 的 `AI_SECRET_ENCRYPTION_KEY` 环境变量中。该密钥用于加密保存的模型 API Key，部署后必须妥善备份；更换或丢失后，已有模型凭证无法解密。

这里的 `192.168.1.30:8080` 是浏览器访问群晖的地址；`RUNTIME_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL` 和 `RUNTIME_BACKEND_API_BASE_URL` 属于容器内回源地址，SQLite 单体版保持镜像默认的 `127.0.0.1:7373` 和 `127.0.0.1:8000`，不需要在 Container Manager 中改成 NAS 地址。

> 截图占位：Container Manager 环境变量列表，展示上述五个关键变量。

## 5. 启动和验证

完成配置后点击“应用/完成”并启动容器，在浏览器访问 `http://NAS地址:8080`。首次登录后立即修改管理员密码。

> 截图占位：Container Manager 容器运行状态、端口和日志页面。

群晖 NAS 必须能够运行该镜像的 CPU 架构并访问 Docker Hub。若镜像下载失败或启动时报架构不兼容，请先确认设备架构和发布镜像支持情况。备份时应覆盖 `/docker/web-presentation/data`，不要删除容器对应的数据目录。
