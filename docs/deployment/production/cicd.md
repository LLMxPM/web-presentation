<!-- 文件功能：说明平台、Runtime、Renderer 镜像构建、发布与生产 compose 部署方式。 -->
# CI/CD 与容器部署说明

## 发布边界

根仓由同一次 Buildx 多架构构建同时发布到 Docker Hub 和阿里云 ACR 个人版。两个仓库使用相同的镜像标签与内容摘要——这依赖 `.github/actions/publish-image` 用单次构建携带双仓标签，而不是分别构建；代价是发布镜像不生成 OCI provenance/SBOM 附件，因为 ACR 个人版不接受该类附件。Docker Hub 作为默认公共仓库，ACR 作为中国大陆网络环境下的拉取副本。镜像仓库为：

- Docker Hub：`docker.io/llmxpm/web-presentation`、`docker.io/llmxpm/web-runtime-vue`、`docker.io/llmxpm/web-presentation-renderer`（**Renderer 尚未发布**，见下）
- 阿里云 ACR：`${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation`、`${ACR_REGISTRY}/${ACR_NAMESPACE}/web-runtime-vue`、`${ACR_REGISTRY}/${ACR_NAMESPACE}/web-presentation-renderer`（**Renderer 尚未发布**）

**关于 Renderer / 自构建 Runtime 镜像的现状（必须如实理解）**：`web-presentation-renderer` 与仓库自构建 `web-runtime-vue` 的推送 job **尚未执行过**，两个 registry 中当前**不可拉取**对应镜像；它们的首次推送预计发生在**下一次 Release**。在首次真实 Release 验证之前，不要按「已存在可拉取的 renderer 镜像」编写部署步骤或回滚组合。

`runtime/` 已 vendored 进本仓，Runtime 独立镜像由本仓 Release 使用 `runtime/Dockerfile` 构建推送，不再依赖外部 `web-runtime-vue` 子模块 SHA 镜像。本仓镜像变体：

- 常规平台镜像：由 `deploy/docker/Dockerfile.platform` 构建，包含 Backend 代码、Editor 静态资源、Nginx 配置和 Backend 运行所需的 Runtime Kit manifest。
- SQLite 轻量单容器镜像：由 `deploy/docker/Dockerfile.lite` 构建，额外内置 Runtime Vite server 运行依赖，面向 SQLite + memory runtime 轻量部署。该变体直接打包当前仓库原生 `runtime/` 源码。**已发布的 `sqlite-lite`（旧架构）自带浏览器，截图在容器内完成**；当前 HEAD 开发中的 lite 渲染能力形态与是否再内置浏览器，以镜像专项计划为准，发布前不要假设 HEAD 与已发布镜像同构。
- 独立 Runtime 运行时镜像：由 `runtime/Dockerfile` 构建（构建上下文为仓库根，以共享 pnpm workspace 锁文件），提供独立 Vite server 以承载生产编排中的预览、诊断与构建接口。**自构建 Runtime 镜像尚未随 Release 推送过**，待下一次 Release 首次发布。

- 独立 Renderer 镜像：由 `renderer/Dockerfile` 在根构建上下文中构建，包含 `wp_renderer` 与 Python Playwright Chromium。**尚未发布；待下一次 Release 首次推送。**

## GitHub Actions

### 质量门禁入口

- 三条流水线共用 `.github/workflows/reusable-quality.yml`，测试命令统一走根目录 `package.json` 的 `test:*` 脚本；workflow 级 `permissions` 收敛为 `contents: read`，每个 job 都带 `timeout-minutes`。
- `platform-test.yml` 的首个 job `test-scope` 执行 `.github/scripts/resolve-test-scope.sh`，由脚本按事件与 `git diff` 产出 `full_tests`、`run_runtime`、`e2e_scope`、`image_matrix` 四个 output。YAML 内不维护第二份路径清单，也不再使用 `dorny/paths-filter`：该 action 在 push 与 schedule 事件没有 diff base 时恒为真，会让每次 main push 都白跑一遍 Runtime 门禁。
- 分级规则：
  - `pull_request` 与 `main` push 以变更文件为输入。只改 `docs/`、`README/AGENTS/DESIGN/LICENSE.md`、`.gitignore`、`.gitattributes` 时只跑快速门禁；其它任何改动进入全量门禁（Backend integration、Runtime 门禁、E2E smoke）。
  - 镜像 smoke 只重建受影响变体：平台镜像构建输入（`deploy/`、`backend/`、`editor/`、`scripts/`、`Dockerfile*`、根 workspace 锁文件、`runtime/package.json`、Runtime Kit manifest）命中则重建平台 + lite；`runtime/` 命中重建 Runtime 镜像与 lite；`renderer/`、`packages/`、`uv.lock` 命中重建 Renderer 镜像。全部 leg 定义在脚本的 `FULL_MATRIX`，由 `tests/contracts/repository/deployment.test.ts` 校验四类交付 Dockerfile 都在其中。
  - 解析不到 diff base（浅克隆、force push、`github.event.before` 不可达）时脚本保守升级为全量，绝不静默降级。
  - `schedule`（每周一）与 `workflow_dispatch` 且 `full_tests=true` 是全量入口：始终跑完整门禁，E2E 使用 `test:e2e:all`，镜像 smoke 覆盖四个变体的多架构构建。
  - `cli-contract` 依赖同级 `web-presentation-agent-kit` 仓库，仅在定时与手动触发。
- 并发分组：`schedule` 使用独立 group 且 `cancel-in-progress=false`，避免定时全量被随后的 main push 中途杀掉；其余事件按 PR 号或 ref 分组并自动取消。
- E2E 在 CI 下允许一次重试（`tests/config/playwright.config.ts` 的 `retries: process.env.CI ? 1 : 0`）：单条用例的定位抖动应在 job 内自愈，不能放大成整套门禁重跑；本地保持 `0` 以暴露真实不稳定。

### Release 流水线

- `platform-release.yml` 不再重复执行整套质量门禁。`verify-main-gate` 通过 `gh api repos/.../actions/runs?head_sha=<发布提交>` 检查该提交是否已有通过的 `platform-test` 运行；没有则拒绝发布。因此**合入 main 的那次 push 必须跑绿**，且 release tag 指向的提交要与该运行同 SHA。确需紧急补发时，需通过 GitHub Actions 页面使用 `workflow_dispatch` 手动触发并勾选 `allow_unverified`（GitHub Release UI 发布无法传入跳过参数），此时写入 `::warning::` 留痕。
- `release-meta` 在构建前一次性校验 `vars.DOCKER_USERNAME`、`secrets.DOCKER_PASSWORD`、`vars.ACR_REGISTRY`、`vars.ACR_NAMESPACE`、`vars.ACR_USERNAME`、`secrets.ACR_PASSWORD` 是否缺失（只做非空判断，不输出值），避免缺配置直到 docker login 阶段才报出难以定位的错误。
- 推送由 `.github/actions/publish-image` composite action 完成：先复用 `.github/actions/check-image` 验证镜像实际启动，再用**一次** `docker/build-push-action` 多架构构建同时携带 Docker Hub 与 ACR 两组标签。代价是关闭 OCI provenance/SBOM 附件（ACR 个人版不接受该附件），换取双仓镜像内容与摘要一致。
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

部署模板、环境变量、启动命令和进程形态详见 [生产部署指南](./README.md) 和 [Compose 部署说明](./compose.md)。

## 关键访问关系

- 浏览器访问简化版的 `platform:80`，或 production env 版的 `gateway:80`。
- 平台 Nginx 代理 `/api`、`/public`、`/build-artifacts`、`/preview`、`/media` 到 `backend:8000`。
- 平台 Nginx 代理 `/runtime/` 到 `runtime:7373`，并保留 `/runtime/` 前缀。
- Backend 通过 `RUNTIME_BASE_URL=http://runtime:7373` 访问 Runtime 内网服务。
- Runtime 通过 `RUNTIME_BACKEND_API_BASE_URL=http://backend:8000` 回源 Backend 内部接口。
- Runtime 通过 `RUNTIME_PREVIEW_JWKS_URL=http://backend:8000/.well-known/jwks.json` 校验 Backend 签发的预览与构建令牌。
