# 飞牛 fnOS 

本页按 fnOS 的可视化 Docker/容器套件编写，不要求 SSH 或命令行。不同 fnOS 版本的菜单名称可能略有差异，但镜像、参数、端口和存储配置保持一致。

## 1. 打开容器套件并拉取镜像

1. 在 fnOS 应用中心安装并打开 Docker/容器管理套件。
2. 进入“镜像”或“镜像仓库”，搜索 `llmxpm/web-presentation`。
3. 选择标签 `sqlite-lite`，点击“拉取/下载”。
4. 等待镜像状态变为可用。

> 截图占位：fnOS 镜像仓库中搜索 `llmxpm/web-presentation:sqlite-lite` 的页面。

## 2. 创建容器

1. 在镜像列表中选中 `llmxpm/web-presentation:sqlite-lite`，点击“创建容器”。
2. 容器名称填写 `web-presentation-lite`。
3. 重启策略选择“除非手动停止”或“始终重启”。
4. 如果套件提供“高级设置”，进入端口、存储和环境变量配置页面。

> 截图占位：fnOS 从镜像创建容器、填写容器名称和重启策略的页面。

## 3. 配置端口和存储

### 端口映射

新增端口映射：

| 主机端口 | 容器端口 | 协议 |
| :--- | :--- | :--- |
| `8080` | `80` | TCP |

如果主机 8080 已被占用，可以使用 `18080`，此时访问地址和环境变量中的端口也要改为 `18080`。

### 存储映射

推荐在 fnOS 中创建专用数据目录，例如 `/vol1/1000/docker/web-presentation/data`，新增目录映射：

| 主机目录 | 容器目录 | 读写 |
| :--- | :--- | :--- |
| `.../web-presentation/data` | `/app/backend/data` | 读写 |

不要只映射 SQLite 文件；整个目录还保存资源、截图、构建产物和 Runtime RSA 私钥。

> 截图占位：fnOS 端口映射和目录映射配置页面。

## 4. 配置环境变量

在“环境变量/变量”页面新增或修改以下变量：

| 变量名 | 示例值 | 作用 |
| :--- | :--- | :--- |
| `BACKEND_PUBLIC_BASE_URL` | `http://192.168.1.20:8080` | 浏览器访问平台的外部入口，系统用它生成平台链接 |
| `RUNTIME_PUBLIC_BASE_URL` | `http://192.168.1.20:8080/runtime` | 浏览器访问 Runtime 预览和资源的外部路径 |
| `CORS_ORIGINS` | `["http://192.168.1.20:8080"]` | 允许访问平台的浏览器来源，必须填写平台外部入口 |
| `DEFAULT_ADMIN_PASSWORD` | 自定义强密码 | 首次登录的默认管理员密码，登录后应立即修改 |
| `AI_SECRET_ENCRYPTION_KEY` | 生成的 Fernet 密钥 | 加密保存模型 API Key，必须长期备份且不能随意更换 |

其余参数使用镜像默认值即可。

### 生成 AI 加密密钥

在自己的电脑上生成密钥，不要使用示例值。电脑已安装 Python 时，在 PowerShell、macOS 或 Linux 终端执行：

```bash
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

复制命令输出的整行内容，粘贴到 fnOS 的 `AI_SECRET_ENCRYPTION_KEY` 环境变量中。该密钥用于加密保存的模型 API Key，部署后必须妥善备份；更换或丢失后，已有模型凭证无法解密。

这里的 `192.168.1.20:8080` 是浏览器访问 fnOS 的地址；`RUNTIME_BASE_URL`、`RUNTIME_PREVIEW_JWKS_URL` 和 `RUNTIME_BACKEND_API_BASE_URL` 属于容器内回源地址，SQLite 单体版保持镜像默认的 `127.0.0.1:7373` 和 `127.0.0.1:8000`，不需要在 fnOS 中改成 NAS 地址。

> 截图占位：fnOS 环境变量列表，展示上述五个关键变量。

## 5. 启动和验证

保存配置并启动容器，在浏览器访问 `http://fnOS地址:8080`。首次登录后立即修改管理员密码。

> 截图占位：fnOS 容器运行状态、端口和健康状态页面。

若启动失败，先检查镜像是否拉取完成、设备 CPU 架构是否受支持、数据目录是否具有读写权限，以及 `CORS_ORIGINS` 是否为合法 JSON 数组。
