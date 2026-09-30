> **归档说明（2026-09-29）**：本文已由新一轮静态评估与计划接替，不再作为现行状态或执行入口。原位置：`docs/temp/image-delivery-research-2026-09-29.md`。历史完成标记、测试结果、发布状态和建议均只代表当时记录；本轮没有重新验证。现行入口：[架构评估](../architecture-assessment-2026-09-30.md) · [改进与下一轮验证计划](../plans/architecture-improvement-plan-2026-09-29.md)。

<!-- 文件功能：镜像交付现状专项调研（实测证据快照，2026-09-29）；供 WS-G1/G3/G5 与专项计划 plans/deployment-image-consolidation-2026-09-29.md 使用。 -->
# 镜像交付现状调研（Lite 单镜像 / Renderer 拆分）

> **日期**：2026-09-29。基线 `3818eab`（分支 `dev`）。对照的已发布版本是 `v0.2.10`（tag 落在 `7fd566b`，2026-09-19；Release run 35511878701 于 2026-09-21 推送镜像）。
> **定位**：专项**调研 / 证据快照**，既不是评估也不是计划。只记录可复核的事实、实测数字与证据链；结论与实施步骤见 [`plans/deployment-image-consolidation-2026-09-29.md`](./deployment-image-consolidation-2026-09-29.md)（**规划 / 未实施**）。
> **本文未改动任何代码、编排或交付配置。**
> **时效**：镜像体积与 registry 可拉取性会随下一次 Release 变化，引用前先按 §10 复核。
> **与现行文档的接口**：为现行计划 [`plans/remaining-work-2026-09-28.md`](./remaining-work-2026-09-28.md) 的 **WS-G1（Lite 故障域）/ G3（密钥治理）/ G5（Renderer 隔离）** 提供输入；并对现行评估 [`architecture-assessment-2026-09-28.md`](./architecture-assessment-2026-09-28.md) §2 第 13 行「Backend 不跑浏览器」补一条**适用层级**说明（见 §7.3）。

---

## 1. 一页结论

1. **HEAD 的整个交付矩阵从未经历过一次真实 Release**。`renderer/wp_renderer`、`packages/render-contracts`、`runtime/Dockerfile`、`deploy/docker/` 布局与 `build-and-push-services` job 全部由 `75af01e`（2026-09-22，仓库结构调整）引入或改造，而最后一次 Release 是 `v0.2.10`（2026-09-21 推送镜像）；`v0.2.10..HEAD` 有 **64 个提交**、无 tag。
2. **`llmxpm/web-presentation-renderer` 在两个 registry 都拉不到**（Docker Hub `object not found` / 匿名 token 取 manifest 401；ACR 匿名 token 后仍 401，对照组同法 200）。而 `deploy/compose/` 下**全部 5 个模板**都引用它 ⇒ 任何新用户照任一 compose 模板都无法完整启动。
3. **已发布的 `sqlite-lite`（645.4 MiB）自带浏览器，且当时浏览器是"在用"的**：`v0.2.10` 的 `backend/pyproject.toml:20` 有 `playwright>=1.60.0`，`Dockerfile.lite:54,90` 设 `PLAYWRIGHT_BROWSERS_PATH` 并执行 `playwright install --with-deps --only-shell chromium`，而当时仓库**既没有 `renderer/` 也没有 `backend/app/services/rendering/`** ⇒ 那是 Backend 进程内截图的旧架构。所以"把 Renderer 合回 lite 镜像"是**第三种形态**（同镜像、独立进程），不是简单回滚。
4. **浏览器栈的实测体积是 225.3 MiB（压缩），不是 GB 级**。`--only-shell chromium`（headless shell）与完整 `chromium` 差别显著，而 `renderer/Dockerfile:26` 现在装的是完整 `chromium`。
5. **唯一未验证的技术前提**：`renderer/wp_renderer/engine/executor.py:298` 是 `chromium.launch(headless=True)`、**无 `--no-sandbox`**，而 `Dockerfile.lite` 与 `renderer/Dockerfile` 都**没有 `USER` 指令**（root 运行）。CI 的镜像 smoke 自己 launch 时传了 `--no-sandbox`，`test:render-e2e` 在非 root runner 上跑 ⇒ **容器内 root 启动 Chromium 这条路径从未被验证过**。这是评估任何合并/发布方案前必须先测的一项。

---

## 2. 交付矩阵现状

| 镜像 | 构建文件 | 谁依赖它 | 最近发布 | 实测体积（压缩） |
| :--- | :--- | :--- | :--- | :--- |
| `llmxpm/web-presentation:latest`（platform/full） | `deploy/docker/Dockerfile.platform` | `compose.yml:17`、`compose.with-deps.yml:54`、`compose.prod.yml:15,22,81`、`compose.runtime-roles.yml:60,69,276` | v0.2.10（2026-09-20） | amd64 **414.0 MiB** / arm64 419.2 MiB |
| `llmxpm/web-presentation:sqlite-lite` | `deploy/docker/Dockerfile.lite` | `compose.sqlite-lite.yml:20`；用户三篇快速部署 | v0.2.10（2026-09-21） | amd64 **645.4 MiB** / arm64 649.4 MiB |
| `llmxpm/web-runtime-vue:latest` | **HEAD 为 `runtime/Dockerfile`；v0.2.10 由外部子模块镜像提供** | `compose.yml:97`、`compose.with-deps.yml:120`、`compose.prod.yml:63`、`compose.runtime-roles.yml:150,206,243` | 2026-09-20（v0.19.3 / `sha-*`） | amd64 **276.8 MiB** / arm64 275.5 MiB |
| `llmxpm/web-presentation-renderer:latest` | `renderer/Dockerfile`（HEAD 新增） | `compose.yml:78`、`compose.with-deps.yml:161`、`compose.prod.yml:45`、`compose.runtime-roles.yml:121`、`compose.sqlite-lite.yml:99` | **从未发布** | **不可拉取** |

发布 job 现状（`.github/workflows/platform-release.yml`）：`build-and-push-services`（矩阵含 `runtime` + `renderer`，:70-86）在 v0.2.10 的 run 中**不存在**——该 run 的 job 列表为 `release-meta / backend-tests / editor-tests / contracts / gateway-contract / validate-runtime-image / build-and-push / build-and-push-lite / e2e-smoke`。PR 侧 `platform-test.yml:80-101` 已含 4 个镜像的构建 smoke 矩阵（含 renderer），但**镜像 smoke 不在 PR 阻塞层**（现行评估 P0-Gates）。

---

## 3. 实测：已发布镜像的层体积

数据来源：Docker Hub Registry v2 API（匿名 pull token）读取 manifest 与 config blob，`history` 中非 `empty_layer` 条目与 `layers` 按序对应。**均为压缩传输体积**，不等于解压后磁盘占用。

`llmxpm/web-presentation:sqlite-lite`（amd64，digest `sha256:4569ecdbf37a8…`，15 层，合计 645.4 MiB）：

| 层 | 体积 | `created_by` |
| :--- | :--- | :--- |
| 9 | **225.3 MiB** | `RUN playwright install --with-deps --only-shell chromium && rm -rf /var/lib/apt/lists/*` |
| 11 | 188.3 MiB | `COPY /app/runtime /app/runtime` |
| 8 | 113.1 MiB | `COPY /app/backend/.venv /app/backend/.venv` |
| 6 | 43.1 MiB | `COPY /usr/local/bin/node /usr/local/bin/node` |
| 0 | 26.9 MiB | Debian bookworm 基础层 |
| 4 | 21.7 MiB | `COPY /uv /uvx /usr/local/bin/` |
| 2 | 13.0 MiB | Python 基础镜像 apt 层 |
| 12 | 4.9 MiB | `COPY /app/editor/dist/ /usr/share/nginx/html/` |

`llmxpm/web-presentation:latest`（platform/full，414.0 MiB）**含同一个 225.3 MiB 浏览器层**（该层在 v0.2.10 的根 `Dockerfile` 中同样存在）⇒ 旧架构下 platform 镜像也自带浏览器。

推论（**推算，非构建实测**）：HEAD 的 lite 去掉了浏览器层、Runtime 改为 `pnpm --filter web-runtime-vue deploy --legacy --prod /out/runtime`（`Dockerfile.lite:38`，剔除 dev 依赖，应小于 188.3 MiB）。若把 headless shell 合并回来，总量约在 **575–650 MiB** 区间，即**与用户今天已经在拉的 645.4 MiB 基本持平**。

复现命令（只读，不拉镜像）：

```bash
TOK=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:llmxpm/web-presentation:pull" | jq -r .token)
curl -s -H "Authorization: Bearer $TOK" -H "Accept: application/vnd.oci.image.index.v1+json" \
  https://registry-1.docker.io/v2/llmxpm/web-presentation/manifests/sqlite-lite
# 取 amd64 digest → 再取该 digest 的 manifest（layers[].size）与 config blob（history[].created_by）
```

---

## 4. Renderer 镜像不可拉取的证据链

四条相互独立的证据，指向同一结论（该镜像从未被成功推送到任何公开仓库）：

1. **Docker Hub repo 不存在**：`GET https://hub.docker.com/v2/repositories/llmxpm/web-presentation-renderer/` → `{"message":"object not found"}`；匿名 pull token 取 `manifests/latest` → **401**。
2. **对照组正常**：同一方法下 `llmxpm/web-presentation` 返回 `is_private: false`、`pull_count: 4647`；`llmxpm/web-runtime-vue` tags 列表可读（`latest` / `v0.19.3` / `sha-*`）。
3. **ACR 同样不可匿名拉取**：`registry.cn-hangzhou.aliyuncs.com` 下按 `Www-Authenticate` 取匿名 token 后，`llmxpm/web-presentation-renderer` → **401**，而 `llmxpm/web-presentation` 与 `llmxpm/web-runtime-vue` → **200**。
4. **发布链路从未执行**：v0.2.10 的 Release run（`gh run view 35511878701`）无 `build-and-push-services` job；`git ls-tree -r v0.2.10 --name-only | grep -c '^renderer/'` → **0**，且 `renderer/Dockerfile`、`runtime/Dockerfile` 在 v0.2.10 均不存在。三者都由 `75af01e`（2026-09-22）引入，晚于该 Release。

**注意这不是"配置错了 tag"**：`docs/developer/deployment/cicd.md:34-56`（renderer 的三个 tag 在 `:37-39` 与 `:47-49`）明确列出稳定 Release 会推送 renderer 的 `<release_tag>` / `latest` / `sha-<commit>`，`:8-9` 还把它写成两个 registry 的既有仓库，workflow 里也确实有对应 step。缺的是**一次真实 Release 去执行它**，以及 ACR 侧仓库可见性的确认（ACR 自动创建的仓库可能默认私有；对照的两个仓库是公开的）。

---

## 5. 文档 / 编排与事实的偏差清单

| # | 位置 | 现在的表述 | 实测事实 | 影响 | 归属 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| B1 | `docs/developer/deployment/cicd.md:8-9`、`:34-56`（renderer tag 在 `:37-39`/`:47-49`）、`:71-72` | 把 renderer 写成两个 registry 的既有仓库，「稳定 Release 会推送」并列为用户可拉取镜像 | 两个 registry 均不可拉取；该 job 从未运行 | 用户按文档部署必失败 | IMG1 |
| B2 | `docs/developer/deployment/README.md:24,51,181`、`compose.md:11,26` | lite = `platform-lite` 容器 + 独立 Renderer 容器；回滚需两 tag 对齐 | Renderer 镜像不存在；已发布的 lite 自带浏览器 | 轻量部署路径整体不可执行 | IMG1 |
| B3 | `deploy/compose/compose.sqlite-lite.yml:99`（及 `compose.yml:78`、`compose.with-deps.yml:161`、`compose.prod.yml:45`、`compose.runtime-roles.yml:121`） | 引用 `llmxpm/web-presentation-renderer:latest` | 拉取失败，`depends_on: condition: service_healthy`（`compose.sqlite-lite.yml:87-89`）使 platform-lite 永不启动 | 5 个模板全部不可用 | IMG1 / IMG2 |
| B4 | `docs/user/quick-deployment/README.md:3`、`docker.md:9-27`、`synology.md`、`fnos.md` | 「三种方式使用同一个镜像」，编排中无 renderer 服务；`docker.md:88` 称数据卷保存"截图" | 与已发布镜像（自带浏览器）一致，**但与 dev HEAD 的 lite 不一致**：HEAD 的 lite 不含浏览器，照此部署则渲染/截图在请求期以 `SERVICE_UNAVAILABLE` 失败（`backend/app/services/rendering/credentials.py:85-129`、`target_resolver.py:48-64`），启动期不报错 | 用户文档在下一版发布后会静默失去渲染能力 | IMG1 / IMG3 |
| B5 | `docs/developer/deployment/cicd.md:108` | 「SQLite 轻量版运行 `platform-lite` 与独立 `renderer` 两个长期容器」 | 同 B2 | 同 B2 | IMG1 |
| B6 | `renderer/README.md:33` | 「Release 与平台、Runtime 同时发布 `web-presentation-renderer:<release_tag>`」 | 尚未发生过 | 交付承诺无证据 | IMG1 |

`RENDER_WORKERS_CONFIG` 的默认值是 `renderer-local` @ `http://127.0.0.1:7400`（`backend/app/core/config.py:135-137`）。在**两容器**形态下该默认值是悬空的（lite 容器内 7400 无监听），必须由 compose 显式覆盖为 `http://renderer:7400`（`compose.sqlite-lite.yml:61`）；在**单容器**形态下它恰好正确。这一点在 §7.4 展开。

---

## 6. Lite 镜像内部结构（现状事实）

`deploy/docker/Dockerfile.lite` 四个 stage：`editor-build`（:4，pnpm 构建 Editor）、`runtime-deps`（:22，`pnpm deploy --legacy --prod /out/runtime`）、`backend-deps`（:41，`uv sync --package backend`；**:51 已 COPY `renderer/pyproject.toml`** 以解析工作区锁）、`lite-runtime`（:56，最终镜像：nginx + node 二进制 + backend venv + runtime + editor dist）。`EXPOSE 80 8000 7373`（:114），入口 `CMD ["sh", "/app/docker/entrypoints/start_lite.sh"]`（:116），**无 `USER` 指令**。

`start_lite.sh` 的进程编排：

| 环节 | 位置 | 事实 |
| :--- | :--- | :--- |
| 迁移 | :82-84 | `alembic upgrade head`（可用 `PLATFORM_LITE_RUN_MIGRATIONS` 关闭） |
| Backend | :86-90 | `uvicorn app.main:app`，单进程（SQLite 单实例边界） |
| Runtime | :92-96 | `cd /app/runtime && node node_modules/vite/bin/vite.js` |
| Gateway | :98-99 | `nginx -g "daemon off;"` |
| 名称解析 | :31-37 | 往 `/etc/hosts` 追加 `127.0.0.1 backend runtime`，以复用平台版 Gateway 配置 |
| 监督 | :103-116 | `while kill -0 …; sleep 2`；**任一进程退出 ⇒ 整容器退出**，无单进程重启 |

编排侧对用户的额外要求：`deploy/compose/compose.sqlite-lite.yml:117-119` 引用 `../secrets/render_service_credential`，而 `.gitignore:32-33` 排除了 `deploy/secrets/`，需用户自行 `openssl rand -base64 48` 生成（`docs/developer/deployment/env-vars.md:80-84`）。**群晖 Container Manager / 飞牛 fnOS 的图形界面无法表达 Docker secret 文件**——用户文档 `synology.md` / `fnos.md` 因此只写单容器流程，这与 B4 是同一个根因。

健康检查：`compose.sqlite-lite.yml:90-96` 串 4 个 URL（Gateway `/healthz`、Backend `/healthz` + `/readyz`、Runtime `/__runtime_healthz`）；镜像 smoke `scripts/contracts/check-image-startup.py:22-27` 的 `lite` 变体探 3 个 URL，且**以 `--network none` 启动**（:34-41），因此从不触达真实渲染。

---

## 7. 把 Renderer 合回 Lite 镜像的可行性核对

### 7.1 依赖与锁：无冲突

`renderer/pyproject.toml` 的运行时依赖是 `fastapi>=0.136.1`、`uvicorn[standard]>=0.47.0`、`pydantic-settings>=2.14.1`、`httpx>=0.28.1`、`render-contracts`、`playwright>=1.60.0`——前五项与 `backend/pyproject.toml` 的约束**完全一致**，唯一新增是 `playwright`。根 `pyproject.toml` 的 workspace members 已含 `backend`、`renderer`、`packages/render-contracts`，**同一份 `uv.lock` 已统一解析三者**。因此单 venv 合并在依赖层面无风险；`Dockerfile.lite:51` 也已为锁解析 COPY 了 `renderer/pyproject.toml`，只需再 COPY `renderer/wp_renderer` 源码。

### 7.2 浏览器体积：`--only-shell` 与 headless-only 一致

`executor.py:298` 只有 `chromium.launch(headless=True)`，不需要有头模式 ⇒ 可用 `--only-shell chromium`（headless shell），即 v0.2.10 已验证过的形态（实测 225.3 MiB）。而 `renderer/Dockerfile:26` 当前是 `playwright install --with-deps chromium`（完整 Chromium，体积更大）。合并时应改回 `--only-shell`，并保留 `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`（`renderer/Dockerfile:12`）。

### 7.3 边界原则的层级澄清（对现行评估 §2 第 13 行的补充）

现行评估把「控制面 / 执行面边界成立：Backend 不跑浏览器（`pyproject.toml` 无 Playwright），渲染只在独立 Renderer」列为**值得保持的结构成果**。这句话有三个层级，必须分开谈，否则"合并镜像"会被误判为推翻该原则：

| 层级 | 现状 | 合并镜像后 | 说明 |
| :--- | :--- | :--- | :--- |
| **进程 / 依赖** | Backend venv 无 Playwright；浏览器只由 `wp_renderer` 进程持有 | **不变**（仍可保持两个 venv 或同 venv 但 Backend 不 import playwright） | 这是原则的实质，`config.py:338-373` 的 fail-closed 校验守的也是这一层（拒绝旧的本机 Playwright 环境变量） |
| **镜像 / 交付** | 两个镜像 | 一个镜像（lite）；生产角色仍用独立 renderer 镜像 | **本文讨论的就是这一层**，与原则不冲突，但需要在评估与 AGENTS.md 措辞上明确"lite 镜像内含 Renderer 进程" |
| **容器 / 运行时隔离** | 两个容器；浏览器与 Backend 分文件系统与环境变量 | 同容器：root 进程可读 `/app/backend/data/*.db` 与 `/proc/1/environ`（含 `AI_SECRET_ENCRYPTION_KEY`） | 这是**唯一真实新增的风险**，见 §8.2；网络层并非新增（自定义 bridge 下 renderer 容器本就可访问 platform-lite 的 8000，`ports:`/`expose:` 不限制容器间互访） |

浏览器侧已有的应用层控制（**与容器拓扑无关，合并不削弱它**）：`executor.py:46-58` 拦截云元数据与链路本地导航主机、导航仅允许 http/https，`_CONTROL_API_PATH_PREFIXES = ("/internal/render/",)` + `:322-331` 的 `page.route("**/*")` abort。注意其覆盖面**只有 Renderer 自己的控制面路径**，不含 Backend 的 `/api/v1`——这与现行评估 **P2-ProdHardening**（`architecture-assessment-2026-09-28.md:99`：「浏览器可触达 Backend 内网 API（仅拦 Renderer 控制面路径）；各 Dockerfile 均无 `USER`（root）」）是同一件事，不是新问题。

### 7.4 凭证与配置：合并反而更简单

- `RENDER_WORKERS_CONFIG` 默认 `127.0.0.1:7400`（`config.py:135-137`）⇒ 单容器下**零配置即正确**；两容器下必须覆盖（`compose.sqlite-lite.yml:61`）。
- `RENDER_SERVICE_CREDENTIAL` 是 fail-closed：缺失、空文件、占位符一律拒绝（`credentials.py:85-129`），所以即使回环调用也必须**有值**。单容器下可由入口脚本首次启动生成并落到 `/app/backend/data`（已在 `lite-data` 卷内，`compose.sqlite-lite.yml:81-82`），从而**消除 `deploy/secrets/` 手工步骤**（NAS 图形界面无法表达，见 §6）。这与 WS-G3（密钥治理）方向一致，但要注意 P1-Secrets（`architecture-assessment-2026-09-28.md:87`）：自动生成必须与"拒绝弱默认密钥"同时成立，不能退化成镜像内固定常量。

---

## 8. 未验证风险

### 8.1 容器内 root 启动 Chromium（**阻塞级，必须先测**）

`executor.py:298` = `chromium.launch(headless=True)`，**未传 `--no-sandbox`**；`renderer/Dockerfile` 与 `deploy/docker/Dockerfile.lite` **都无 `USER`**（root 运行）。CI 覆盖不到这条路径：`check-image-startup.py:54-63` 的 renderer 分支是脚本**自己**以 `args=['--no-sandbox']` 启动 Chromium，只验证"浏览器装上了"，不验证 `wp_renderer` 的真实启动参数；`test:render-e2e` 在 runner 上以非 root 执行。root + 默认 seccomp 下 Chromium 常因 setuid / user-namespace sandbox 拒绝启动。

**判定**：这是"合并进 lite"和"首次发布 renderer 镜像"**共同**的前置验证项，不是合并独有的成本。解法二选一——加 `--no-sandbox`（与 §7.3 的风险接受口径一致）或加非 root `USER` + 相应权限；两者都影响 P2-ProdHardening / WS-G5 的结论，应一次定稿。

### 8.2 同容器的文件系统与环境变量暴露

合并后，渲染**用户与 AI 生成的页面代码**的浏览器进程与 Backend 同处一个文件系统，且为 root：可读 `/app/backend/data/web_presentation.db`（含各用户数据与加密后的模型凭证）、`/proc/1/environ`（含 `AI_SECRET_ENCRYPTION_KEY`）。在"自用 / 团队内部"的威胁模型下可接受；**当 lite 实例开放多用户、且低权限成员的页面代码会在其中渲染时，这构成跨用户越权**，此时 §7.3 第三层的隔离必须重新成立（独立容器或非 root + 只读挂载）。

### 8.3 下一次 Release 是多个"首次"

`v0.2.10` 之后无 Release，所以下一次 Release 将同时首次执行：`build-and-push-services`（renderer + 自构建 runtime 镜像）、`deploy/docker/` 新布局下的 platform/lite 构建、ACR 侧两个新仓库的自动创建与可见性。**任一环节失败都会让 5 个 compose 模板继续不可用**，且 `platform-test.yml` 的镜像 smoke 不在 PR 阻塞层（P0-Gates），漂移可能已合入。建议按专项计划 IMG1/IMG2 做一次发布预演，而不是等正式 Release 暴露。

---

## 9. 已被推翻或需修正的论点（防重提）

| 论点 | 出处 | 实测结论 |
| :--- | :--- | :--- |
| 「合并浏览器会让 lite 镜像涨到 GB 级」 | 本次讨论首轮（无实测） | **错**。浏览器栈实测 **225.3 MiB**（`--only-shell chromium` + apt 依赖，压缩）；合并后总量约 575–650 MiB，与用户今天已拉的 645.4 MiB 持平 |
| 「合并后浏览器才碰得到控制 API」 | 本次讨论首轮 | **不准确**。自定义 bridge 网络下 renderer 容器本来就能访问 platform-lite 的 8000；合并真正新增的是**文件系统与 PID1 环境同处**（§8.2）。且浏览器侧已有 route 拦截（`executor.py:322-331`），其覆盖面只有 `/internal/render/`，与拓扑无关 |
| 「Chromium OOM 会连累持 SQLite 的 Backend，所以不该同容器」 | 本次讨论首轮 | **不成立**。Runtime Vite build worker 的 `--max-old-space-size` 已是 1024 MB、构建超时 600s（`compose.sqlite-lite.yml:49-50`），比 headless shell 更重，且**今天已经与 Backend 同 cgroup**——该风险是既已接受的现状。另外 Chromium 崩溃发生在 attempt 内部（每 attempt 新建浏览器），会被转成渲染错误返回，不会让 uvicorn 退出，因此不给 `start_lite.sh:103-116` 的监督循环增加新触发源 |
| 「合并 = 回到已发布形态」 | 本次讨论第二轮 | **需修正**。已发布的 v0.2.10 是**Backend 进程内 Playwright**（`backend/pyproject.toml:20`），被现行架构显式禁止（`config.py:338-373`）。合并方案是"同镜像 + 独立 Renderer 进程"的**第三种形态**，是新工作，不是回滚 |
| 「lite 拆分后用户需要处理两个镜像」 | `docs/developer/deployment/README.md:181` 等 | 事实更强：**用户根本拿不到第二个镜像**（§4）。当前唯一能跑通的用户路径是已发布的旧架构单镜像 |

---

## 10. 复核条件与失效触发

本文的下列断言**会随时间失效**，引用前必须复核：

| 断言 | 复核方法 | 失效触发 |
| :--- | :--- | :--- |
| renderer 镜像不可拉取 | §4 的 Hub / ACR 匿名 token 探测 | 任何一次成功的 `build-and-push-services` 之后立即失效 |
| 镜像体积数字 | §3 的 registry API 层清单 | 下一次 Release（新层、新基础镜像、`--only-shell` 变更） |
| 「HEAD 交付矩阵未经 Release」 | `gh run list --workflow=platform-release.yml` + `git tag --contains 75af01e` | 出现 ≥ `75af01e` 的 tag |
| root + 无 `--no-sandbox` 未验证 | 读 `executor.py:298` 与两个 Dockerfile 的 `USER`；或跑 IMG0 实测 | 任一处改动后即需重测 |
| 偏差清单 B1–B6 | 逐条读对应 `file:line` | 文档修订后按 `test:repository` 的链接门禁复核 |

`pnpm run test:repository` 只检查 Markdown 相对链接与代码围栏闭合（`tests/contracts/repository/documentation.test.ts:13-41`），**不校验本文的事实断言**；事实复核只能靠上表的方法。

---

## 11. 未覆盖项（按 README 维护约定 4，自动进入专项计划）

1. **arm64 侧未逐层核对**：只取了 per-arch 总体积（649.4 / 419.2 / 275.5 MiB），未分解层；NAS 市场 arm64 占比高，合并方案的体积结论应在 arm64 上复测。
2. **解压后磁盘占用与内存占用均未测**：本文只有压缩传输体积；WS-G1 的"故障域与规模承诺"需要 RSS/OOM 数据，那属于 WS-D1（Lite 2C4G 两轮基线）的范围。
3. **ACR 仓库可见性规则未确认**：只证明了"匿名拉不到"，未确认是"仓库不存在"还是"存在但私有"，也未确认 ACR 命名空间的默认可见性策略。
4. **`runtime/Dockerfile` 自构建镜像未与已发布的 `web-runtime-vue`（外部子模块构建）对比**：两者内容可能不等价，下一次 Release 会首次替换，需要独立的启动与渲染验证。
5. **未实测构建**：本次调研全部基于 registry API、git 历史、workflow 与 CI run 记录，**没有执行任何 `docker build`**；合并后的真实体积与构建时长仍是推算。
6. **多架构 QEMU 构建时长未评估**：`platform-release.yml:137,151,221,235,305,319` 对 platform/lite 都是 amd64+arm64；把浏览器加回 lite 会显著增加 arm64 的 QEMU 构建时间，可能触及 GitHub Actions 超时，需要预演数据。
