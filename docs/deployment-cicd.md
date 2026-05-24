<!-- 文件功能：说明平台镜像构建、Docker Hub 发布、Runtime 子项目镜像耦合和生产 compose 部署方式。 -->
# CI/CD 与容器部署说明

## 发布边界

根仓只发布一个平台镜像：`web-presentation`。该镜像同时包含 Backend 代码、Editor 静态资源、Nginx 配置和 Backend 运行所需的 Runtime Kit manifest。

`runtime/` 仍是独立项目 `web-runtime-vue` 的子模块接入目录。根仓不会构建 Runtime 镜像，只会在平台 Release 前校验当前子模块 SHA 对应的 Runtime 镜像已存在：

```bash
docker buildx imagetools inspect docker.io/$DOCKERHUB_NAMESPACE/web-runtime-vue:sha-<runtime_sha_short>
```

`web-runtime-vue` 子仓库自己的 Docker Release 会发布 `<release_tag>`、`sha-<runtime_sha_short>`，稳定 Release 还会发布 `latest`。平台仓库更新 `runtime` 子模块指针前，应先让对应 Runtime 提交完成子仓库 Release。

## GitHub Actions

- PR：`.github/workflows/platform-test.yml` 继续执行 backend、editor、contracts、e2e smoke，并新增平台镜像 build smoke；该任务只构建，不推送。
- Release：`.github/workflows/platform-release.yml` 在 GitHub Release `published` 后执行完整质量门禁、Runtime 镜像存在性校验，然后推送 Docker Hub。
- Docker Hub 配置：
  - `vars.DOCKERHUB_NAMESPACE`
  - `vars.DOCKER_USERNAME`
  - `secrets.DOCKER_PASSWORD`

稳定 Release 会推送：

```text
docker.io/<namespace>/web-presentation:<release_tag>
docker.io/<namespace>/web-presentation:latest
```

Pre-release 只推送版本标签，不移动 `latest`。

## 生产 Compose

生产模板为 `docker-compose.prod.yml`，示例环境变量见 `deploy/.env.prod.example`。

```bash
docker compose --env-file deploy/.env.prod.example -f docker-compose.prod.yml config
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

正式部署前必须替换数据库密码、默认管理员密码和 `AI_SECRET_ENCRYPTION_KEY`；Fernet 密钥可用 `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成。

同一个平台镜像会启动两个容器：

- `backend`：执行 `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `gateway`：执行 `nginx -g 'daemon off;'`，托管 Editor 并代理 Backend/Runtime

`WEB_RUNTIME_IMAGE` 必须固定到 Runtime 子项目发布的 SHA 标签，例如：

```text
WEB_RUNTIME_IMAGE=your-dockerhub-namespace/web-runtime-vue:sha-c5273cf1564d
```

## 关键访问关系

- 浏览器访问 `gateway`。
- `gateway` 代理 `/api`、`/public`、`/build-artifacts`、`/preview`、`/media` 到 `backend:8000`。
- `gateway` 代理 `/runtime/` 到 `runtime:7373`，并去掉 `/runtime/` 前缀。
- Backend 通过 `RUNTIME_BASE_URL=http://runtime:7373` 访问 Runtime 内网服务。
- Runtime 通过 `RUNTIME_BACKEND_API_BASE_URL=http://backend:8000` 回源 Backend 内部接口。
- Runtime 通过 `RUNTIME_PREVIEW_JWKS_URL=http://backend:8000/.well-known/jwks.json` 校验 Backend 签发的预览与构建令牌。
