<!-- 文件功能：说明平台、Runtime、Renderer 镜像构建、发布与生产 compose 部署方式。 -->
# CI/CD 与容器部署说明

## 发布边界

根仓由同一次 Buildx 多架构构建同时发布到 Docker Hub 和阿里云 ACR 个人版。两个仓库使用相同的镜像标签与内容摘要；Docker Hub 作为默认公共仓库，ACR 作为中国大陆网络环境下的拉取副本。镜像仓库为：

- Docker Hub：`docker.io/llmxpm/web-presentation`、`docker.io/llmxpm/web-runtime-vue`、`docker.io/llmxpm/web-presentation-renderer`（**Renderer 尚未发布**，见下）
- 阿里云 ACR：`${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation`、`${ACR_REGISTRY}/${ACR_NAMESPACE}/web-runtime-vue`、`${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation-renderer`（**Renderer 尚未发布**）

**关于 Renderer / 自构建 Runtime 镜像的现状（必须如实理解）**：`web-presentation-renderer` 与仓库自构建 `web-runtime-vue` 的推送 job **尚未执行过**，两个 registry 中当前**不可拉取**对应镜像；它们的首次推送预计发生在**下一次 Release**。在首次真实 Release 验证之前，不要按「已存在可拉取的 renderer 镜像」编写部署步骤或回滚组合。

`runtime/` 已 vendored 进本仓，Runtime 独立镜像由本仓 Release 使用 `runtime/Dockerfile` 构建推送，不再依赖外部 `web-runtime-vue` 子模块 SHA 镜像。本仓镜像变体：

- 常规平台镜像：由 `deploy/docker/Dockerfile.platform` 构建，包含 Backend 代码、Editor 静态资源、Nginx 配置和 Backend 运行所需的 Runtime Kit manifest。
- SQLite 轻量单容器镜像：由 `deploy/docker/Dockerfile.lite` 构建，额外内置 Runtime Vite server 运行依赖，面向 SQLite + memory runtime 轻量部署。该变体直接打包当前仓库原生 `runtime/` 源码。**已发布的 `sqlite-lite`（旧架构）自带浏览器，截图在容器内完成**；当前 HEAD 开发中的 lite 渲染能力形态与是否再内置浏览器，以镜像专项计划为准，发布前不要假设 HEAD 与已发布镜像同构。
- 独立 Runtime 运行时镜像：由 `runtime/Dockerfile` 构建（构建上下文为仓库根，以共享 pnpm workspace 锁文件），提供独立 Vite server 以承载生产编排中的预览、诊断与构建接口。**自构建 Runtime 镜像尚未随 Release 推送过**，待下一次 Release 首次发布。

- 独立 Renderer 镜像：由 `renderer/Dockerfile` 在根构建上下文中构建，包含 `wp_renderer` 与 Python Playwright Chromium。**尚未发布；待下一次 Release 首次推送。**

## GitHub Actions

- 质量门禁共用 `.github/workflows/reusable-quality.yml`，测试命令统一走根目录 `package.json` 的 `test:*` 脚本。
- PR：`platform-test.yml` 调用 reusable-quality 执行快速门禁（Backend unit/api、Editor、contracts、render-contracts、renderer、gateway）；当 `runtime/` 或根 pnpm workspace、锁文件、工具链配置变化时，额外执行 Runtime 门禁。
- 全量测试：`platform-test.yml` 在 `main` push、每周一定时任务或手动触发且 `full_tests=true` 时，在快速门禁基础上补充 Backend integration、Runtime 门禁、E2E，以及平台 / lite / runtime / renderer 四类镜像构建与实际启动 smoke（不推送）。定时与手动还会执行全部 E2E project；`cli-contract` 仅在定时/手动触发（依赖外部 agent-kit 仓库）。
- Release：`platform-release.yml` 先调用 reusable-quality（`full=true`，E2E 全量），通过后构建镜像并复用 `.github/actions/check-image` 验证实际启动，再由本仓推送 Runtime、Renderer、常规平台、SQLite 轻量四类镜像到 Docker Hub 与阿里云 ACR。
- Docker Hub 配置：
  - `vars.DOCKER_USERNAME`
  - `secrets.DOCKER_PASSWORD`
- 阿里云 ACR 配置：
  - `vars.ACR_REGISTRY`：个人版实例访问域名，例如 `crpi-xxxx.cn-hangzhou.personal.cr.aliyuncs.com`，不要填写 `https://`。
  - `vars.ACR_NAMESPACE`：阿里云 ACR 命名空间。
  - `vars.ACR_USERNAME`：ACR 访问凭证中的登录名。
  - `secrets.ACR_PASSWORD`：ACR 访问凭证密码，不是阿里云控制台登录密码。

稳定 Release 的目标推送清单如下。其中 **`web-presentation-renderer` 与 `web-runtime-vue`（自构建）两类镜像尚未发布；下列 renderer / runtime 行描述的是「待下一次 Release 首次推送」的计划，不是当前已可拉取的标签**：

```text
docker.io/llmxpm/web-presentation-renderer:<release_tag>
docker.io/llmxpm/web-presentation-renderer:latest
docker.io/llmxpm/web-presentation-renderer:sha-<commit_sha>
docker.io/llmxpm/web-runtime-vue:<release_tag>
docker.io/llmxpm/web-runtime-vue:latest
docker.io/llmxpm/web-runtime-vue:sha-<commit_sha>
docker.io/llmxpm/web-presentation:<release_tag>
docker.io/llmxpm/web-presentation:latest
docker.io/llmxpm/web-presentation:sqlite-lite-<release_tag>
docker.io/llmxpm/web-presentation:sqlite-lite
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation-renderer:<release_tag>
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation-renderer:latest
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation-renderer:sha-<commit_sha>
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-runtime-vue:<release_tag>
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-runtime-vue:latest
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-runtime-vue:sha-<commit_sha>
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation:<release_tag>
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation:latest
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation:sqlite-lite-<release_tag>
${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation:sqlite-lite
```

Pre-release 只推送固定版本标签，不移动 `latest` 与 `sqlite-lite`。

## 生产 Compose

生产部署不在目标机器构建镜像，只拉取 CI/CD 已发布的业务镜像。默认使用 Docker Hub；中国大陆网络环境可以将 Compose 中的平台镜像替换为 ACR 地址。当前**已发布、可拉取**的平台镜像仓库为：

- `llmxpm/web-presentation:latest`
- `llmxpm/web-presentation:sqlite-lite`
- `${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation:latest`
- `${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation:sqlite-lite`

下列镜像在文档/模板中被引用，但**尚未发布、当前不可拉取**（待下一次 Release 首次推送）；在首次发布预演通过前，引用它们的 compose 模板不能视为开箱即用：

- `llmxpm/web-runtime-vue:latest` / `${ACR_REGISTRY}/${ACR_NAMESPACE}/web-runtime-vue:latest`
- `llmxpm/web-presentation-renderer:latest` / `${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation-renderer:latest`

部署模板集中在 `deploy/` 目录：

> **模板可用性（B3）**：`deploy/compose/` 下 5 个模板均引用 `web-presentation-renderer` / 自构建 `web-runtime-vue` 镜像。这些镜像**尚未发布、当前不可拉取**，因此模板**不是开箱即用**；需待下一次 Release 发布预演通过、镜像可匿名拉取后，才能按下列模板直接部署。已发布且可直接使用的轻量路径是用户文档中的单容器 `sqlite-lite`（不引用 renderer 镜像），见[快速部署](../../user/quick-deployment/README.md)。

- `deploy/compose/compose.yml`：外部 PostgreSQL/Redis 简化版，环境变量直接写在 compose 内。
- `deploy/compose/compose.sqlite-lite.yml`：SQLite + memory runtime 轻量版，使用 `llmxpm/web-presentation:sqlite-lite`；模板另含 `renderer` 服务定义，但对应镜像尚未发布（见上），**该模板在 renderer 首次推送前不可直接 `pull` 启动**。已发布的 `sqlite-lite` 用户路径见[快速部署](../../user/quick-deployment/README.md)（单容器、镜像内置浏览器）。
- `deploy/compose/compose.with-deps.yml`：内置 PostgreSQL/Redis 简化版，随应用一起启动 PostgreSQL 与 Redis，环境变量直接写在 compose 内。
- `deploy/compose/compose.prod.yml`：runtime-all 兼容/Lite 生产版，拆分迁移、Backend、Runtime、Renderer 与 Gateway，并通过 `env_file: ../.env` 读取 `deploy/.env`；适合小团队或尚未分角色的环境。
- `deploy/compose/compose.runtime-roles.yml`：**官方生产主路径**，分角色单机版，`runtime-preview` / `runtime-build` / `runtime-check` 各一实例，附每角色 CPU/内存 limits 与执行预算，Gateway 只代理预览；Backend 读取 `deploy/.env`，Runtime 角色只读取 `deploy/runtime.env`。
- `deploy/.env.example`：供 production env 版与分角色单机版的 Backend 复制为 `deploy/.env` 使用。
- `deploy/runtime.env.example`：供分角色单机版的 Runtime 复制为 `deploy/runtime.env` 使用，不包含平台密钥。

SQLite 轻量单容器版启动方式：

```bash
cd deploy
docker compose -f compose/compose.sqlite-lite.yml config
docker compose -f compose/compose.sqlite-lite.yml pull
docker compose -f compose/compose.sqlite-lite.yml up -d
```

内置依赖简化版启动方式：

```bash
cd deploy
docker compose -f compose/compose.with-deps.yml config
docker compose -f compose/compose.with-deps.yml pull
docker compose -f compose/compose.with-deps.yml up -d
```

外部依赖简化版使用默认 `compose/compose.yml`；production env 版需要先复制 `deploy/.env.example` 为 `deploy/.env`，再将命令中的 compose 文件改为 `compose/compose.prod.yml`。所有模板的共享密钥文件位于 `deploy/secrets/render_service_credential`，Compose 使用 `../secrets/render_service_credential` 引用。创建方法见 [环境变量说明](./env-vars.md)。完整部署、升级、回滚和运维检查流程见 [生产部署指南](./README.md)。

正式部署前必须替换数据库密码、默认管理员密码和 `AI_SECRET_ENCRYPTION_KEY`。`AI_SECRET_ENCRYPTION_KEY` 必须是 Fernet 密钥，即 32 字节随机值的 URL-safe base64 编码，通常长度为 44 个字符并以 `=` 结尾；可用 `python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` 生成。部署后应长期保存，随意更换会导致已有用户模型凭证密文无法解密。

AI 会话、run、事件、消息、工具调用和 HITL 状态写入 Backend 主库中的 `ai_agent_*` 表，随常规数据库备份和 Alembic 迁移一起管理。

SQLite 轻量版的进程形态分两种口径，不要混用：

- **已发布 `sqlite-lite`（当前用户可拉取）**：**一个** `platform-lite` 长期容器，入口脚本执行 `alembic upgrade head` 后同时启动 uvicorn、Vite 与 Nginx，**截图由镜像内置浏览器完成**，不依赖独立 Renderer 容器、也不需要 `deploy/secrets/` 渲染凭证文件。
- **HEAD compose 模板形态（待发布预演）**：`compose.sqlite-lite.yml` 另起独立 `renderer` 容器执行截图；但 renderer 镜像**尚未发布、当前不可拉取**，该「平台 + renderer」双容器组合在首次 Release 推送前不能作为已交付形态宣传。

`platform-lite` 容器入口脚本会先执行 `alembic upgrade head`，再同时启动：

- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
- `node node_modules/vite/bin/vite.js`
- `nginx -g 'daemon off;'`

两个常规简化版中，同一个平台镜像只启动一个长期运行的 `platform` 容器。该容器入口脚本会先执行 `alembic upgrade head`，再同时启动：

- `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
- `nginx -g 'daemon off;'`

production env 版中，同一个平台镜像会拆分为三个容器：

- `backend-migrate`：执行 `alembic upgrade head`
- `backend`：执行 `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
- `gateway`：执行 `nginx -g 'daemon off;'`，托管 Editor 并代理 Backend/Runtime

Renderer 镜像**尚未发布**。待下一次 Release 首次推送后，生产角色部署才需要把 Renderer 固定为 `llmxpm/web-presentation-renderer:<release_tag>`，并与平台和 Runtime 一起升级或回滚。

常规 compose 默认跟随 `latest`，SQLite 轻量 compose 默认跟随 `sqlite-lite`。需要严格锁定版本时，常规部署应同时固定平台、Runtime 与 Renderer 的 `<release_tag>`（Renderer 以实际已发布标签为准）；已发布的轻量版只需固定 `sqlite-lite-<release_tag>`。不要只回滚其中一个业务镜像；数据库迁移一旦前进，平台镜像必须仍然包含数据库 `alembic_version` 指向的 revision 文件。

## 关键访问关系

- 浏览器访问简化版的 `platform:80`，或 production env 版的 `gateway:80`。
- 平台 Nginx 代理 `/api`、`/public`、`/build-artifacts`、`/preview`、`/media` 到 `backend:8000`。
- 平台 Nginx 代理 `/runtime/` 到 `runtime:7373`，并保留 `/runtime/` 前缀。
- Backend 通过 `RUNTIME_BASE_URL=http://runtime:7373` 访问 Runtime 内网服务。
- Runtime 通过 `RUNTIME_BACKEND_API_BASE_URL=http://backend:8000` 回源 Backend 内部接口。
- Runtime 通过 `RUNTIME_PREVIEW_JWKS_URL=http://backend:8000/.well-known/jwks.json` 校验 Backend 签发的预览与构建令牌。
