<!-- 文件功能：本轮唯一现行执行计划；收敛部署形态为生产与 Lite 两种、把 Lite 合并回单镜像，并承接环境变量治理与配置 Web UI 迁移。 -->
# 部署形态收敛与配置治理工作计划

更新日期：2026-10-02。本文是本轮唯一执行入口，面向仓库开发与验收，确定范围、批次、停止条件和证据要求。上一轮架构收尾的 M01–M08 已全部关闭，见[已归档收尾计划](../archive/architecture-closeout-plan-2026-10-01.md)；本轮由该计划 §9「部署形态发生实质变化」的复审触发条件开出。

编号约定：批次用 **B0–B6**，工作项用 **DEP\*（部署收敛）/ CFG\*（配置治理）/ GAT\*（门禁）**，决策用 **D-Dep\* / D-Cfg\***，风险用 **R-Dep\* / R-Cfg\***；重开的门沿用上一轮 **M01 / M03 / M06 / M07** 编号并加撇号（M01′），便于对照复用依据。历史镜像工作项 **IMG0–IMG12** 的接续映射见 §8。

---

## 1 一页结论

1. **本轮把「Lite 单镜像」与「环境变量治理」合成一件事做。** 治理规划的最终形态是 Lite 只剩一个容器、零密钥文件、零必填变量；而当前 `deploy/docker/Dockerfile.lite` 既没有浏览器也没有 `wp_renderer`。若只做模板瘦身而不合并镜像，会得到一个能启动、能编辑、但截图与渲染**静默不可用**的 Lite。合并镜像不是可选优化，是治理目标成立的前置条件。
2. **镜像形态是回归，进程形态是新的。** 已发布 v0.2.10 的 `Dockerfile.lite:90` 就是 `playwright install --with-deps --only-shell chromium`，单容器自带浏览器，体积约 645 MiB（压缩），与用户今天已经在拉的镜像持平——**但那是 Backend 进程内驱动 Playwright 的旧形态**（v0.2.10 的 `backend/pyproject.toml:20` 声明 `playwright>=1.60.0`，且当时仓库没有 `renderer/` 目录），已被 AGENTS.md 与归档计划 §7-1 明确禁止恢复。本轮要做的是「单镜像 + 独立 Renderer 进程」的新组合：浏览器层与容器数量的结论可以沿用实测，**进程拓扑的结论不能**，M01′/M03′/M06′/M07′ 必须重跑。
3. **阻塞已解除。** 归档镜像计划的三个前置——任务运行时契约冻结、Lite 容量基线、Renderer 隔离决策 G5——现在都有结论（M03 已关闭并给出 2C4G 推荐配置；[Lite 隔离决策](../../developer/deployment/lite-scale-and-isolation.md) §3/§4 已定 G1 不拆容器、G5 风险接受）。IMG0–IMG12 的分析可直接复用，不重新论证。
4. **唯一未验证的硬阻塞是 B0**：容器内 root 起 Chromium。`renderer/wp_renderer/engine/executor.py:307` 是 `chromium.launch(headless=True)`，无 `--no-sandbox`，而 `Dockerfile.lite` 与 `renderer/Dockerfile` 都没有 `USER` 指令；`scripts/contracts/check-image-startup.py:163-169` 的 renderer 分支自己 launch 并代传 `--no-sandbox`，**照不到真实启动路径**。B0 不通则 B1 退回双容器形态，治理规划的 Lite 最终形态要改回带 renderer 服务。
5. **本轮会重开四个已关闭的门**（M01′/M03′/M06′/M07′，见 §5）。归档收尾计划 §6 原文写明「两容器结果不能给单容器合并形态背书」，`lite-scale-and-isolation.md` §5 也要求镜像形态变更时更新该文 §2–§4。重开是既定口径，不是返工。

---

## 2 现状与目标形态

### 2.1 现状清单

代码层早已只有两种形态：`backend/app/db/profile.py` 只识别 `sqlite-lite` 与 `postgresql-distributed`，判定纯配置派生（`DATABASE_URL` 前缀 + `backend_multi_instance` + `WEB_CONCURRENCY/UVICORN_WORKERS`）。需要收敛的是交付层：

| 交付面 | 现状 | 问题 |
| :--- | :--- | :--- |
| compose 模板 | 5 个：`compose.yml`（外部依赖简化版）、`compose.with-deps.yml`（自带 PG/Redis）、`compose.prod.yml`（单 Runtime 全角色）、`compose.runtime-roles.yml`（7 服务分角色）、`compose.sqlite-lite.yml`（Lite 两容器） | 前两个与 `prod.yml` 能力重叠；文档口径并存三套数字（`compose.md:3`「五类」、`cicd.md:79`「5 个」、`runs/2026-10-01-m03-m06` 报告「4 套」） |
| 镜像 | 4 个：`web-presentation`（platform）、`web-runtime-vue`、`web-presentation-renderer`、`web-presentation:sqlite-lite` | renderer 镜像从未成功发布，两个 registry 都拉不到；5 个模板全部引用它 |
| 对外变量 | `deploy/.env.example` 96 项、`deploy/runtime.env.example` 19 项、`AppSettings` 155 字段 | Audience、租约、心跳、轮询、Worker 内存比例等微观参数与必填项混排 |
| 密钥 | `AI_SECRET_ENCRYPTION_KEY` 有硬编码默认值（`config.py:158`）但被 `signing_identity.py:26,361-370` 当占位符 fail-closed 拒绝；`RENDER_SERVICE_CREDENTIAL` 要求手工建文件并设 `0400` | 部署前必须跑 Python 生成 Fernet 密钥、手工建 secret 文件，格式稍错即拒绝启动 |

### 2.2 目标形态

| 维度 | 目标 |
| :--- | :--- |
| 部署方式 | **只有两种**：生产（PostgreSQL + Redis，多容器）与 Lite（SQLite + memory，单容器） |
| 生产模板 | 保留 `compose.prod.yml`（小团队，单 Runtime 全角色）与 `compose.runtime-roles.yml`（分角色，最小权限 runtime.env + 独立网络与 limits），二者同属「生产」；删除 `compose.yml` 与 `compose.with-deps.yml` |
| Lite 镜像 | 单镜像内含 Backend + Editor + Runtime + Renderer（浏览器）+ Nginx Gateway；单容器 4 个长期进程；零密钥文件 |
| 必填变量 | Lite：0 项（`docker compose up -d` 即可）；生产：类 A 约 9 项 |
| 业务配置 | 存储、时区、会话策略、AI 运营、日志级别全部迁入 Web UI，热更新生效，无进程重启 |

---

## 3 已定决策

| ID | 决策 | 定案日期与依据 | 复审触发 |
| :--- | :--- | :--- | :--- |
| **D-Dep1** | 生产侧保留 `compose.prod.yml` + `compose.runtime-roles.yml` 两个模板（同属「生产」的两种规模），删除 `compose.yml` 与 `compose.with-deps.yml` | 2026-10-02 用户拍板 | 若 with-deps 的 PG/Redis 自备能力缺失导致 PG 侧备份恢复与密钥轮换 runbook 无法复现（见 R-Dep2），则改为把该能力以文档片段或 profile 形式补回 |
| **D-Dep2** | Lite 与独立 renderer 两侧的 Chromium 安装参数**统一为 `--only-shell chromium`** | 2026-10-02 用户拍板；依据 `executor.py:307` 只有 `headless=True` 一条路径，v0.2.10 已发布 Lite 用的正是该参数 | 若 B4 实测发现任一渲染路径需要完整 chromium（有头、channel、PDF 打印等），则 renderer 侧回退完整安装并由 GAT3 记录两侧差异 |
| **D-Cfg1** | **删除**治理规划原 §3.2 的「第二层优雅重启」与 `POST /api/v1/admin/system/restart` | 2026-10-02 用户拍板；类 A（含 `CORS_ORIGINS`、`SESSION_SECURE`）本就在 ENV，Web UI 改不到，第二层没有触发场景；且多副本生产下「重启一个 Backend 实例」语义不成立（`multi-backend.md`） | 若 B5 实施中发现某个类 B 配置确实在 FastAPI 启动期绑定且无法热替换，则该项改归类 A 并在文档写明「改 .env + 重启容器」，不重新引入 restart API |
| **D-Dep3** | Lite 单镜像采用**双 venv**：`/app/.venv`（Backend，不含 playwright）+ 独立 Renderer venv（含 playwright 与 `wp_renderer`） | 2026-10-02 用户拍板，选择「不改文档」：保住 `lite-scale-and-isolation.md:39`「Backend venv 仍无 Playwright」与 AGENTS.md「Backend 不安装 Playwright/Chromium」的依赖层表述，使该边界可被静态检查。已知代价：镜像约多 60–100 MiB（fastapi/uvicorn/pydantic/httpx 重复一份），多一次 `uv sync`，arm64 构建时长增加（计入 R-Dep5） | 若合并后 Lite 压缩体积 > 800 MiB（触发 D-Img1 复审），或 arm64 构建时长导致 Release 超时且缓存无法解决，则重开本决策并评估改单 venv + 改写依赖层承诺 |
| **D-Img1=C** | Lite 内含 Renderer 进程，同时继续发布独立 renderer 镜像供生产角色使用（双轨） | 沿用[归档镜像计划](../archive/deployment-image-consolidation-2026-09-29.md) §2 推荐；G5 已选风险接受 | 见归档计划 §2 的 5 条触发条件；本轮新增：合并后 Lite 压缩体积 > 800 MiB |

---

## 4 执行批次

以下是连续投入时的工作量预算，执行日从实际开始计算，不作为日历承诺。B0–B4 合计约 9–13 个工作日（交付面收敛与重开验收），B5–B6 约 7–10 个工作日（配置中心与动态运营）。B1 与 B2 动同一批文件，应合并为一次提交与一轮门禁。

| 批次 | 预算 | 优先工作 | 出口 |
| :--- | :--- | :--- | :--- |
| **B0** 阻塞验证 | 0.5 天 | DEP0 容器内 root 起 Chromium 真实路径 | 得到「能/不能」确定结论；不能则定稿 `--no-sandbox` 还是非 root `USER`，并把 B1 退回双容器形态 |
| **B1** 交付面收敛 | 2–3 天 | DEP1 删模板 + DEP2 合并镜像 + DEP3 入口第 4 进程 + DEP4 编排默认值 + DEP5 浏览器参数统一 | 3 个模板、4 个 Dockerfile 自洽；`docker compose config` 与镜像 smoke 通过 |
| **B2** 零密钥启动 | 1–2 天 | CFG1 密钥自动生成（三类分治）+ CFG1a 占位符清单补漏 + CFG2 模板瘦身 + CFG3 runtime.env 密钥边界门禁 | Lite 零必填变量、零 secret 文件即可完整可用（含截图） |
| **B3** 门禁与文档 | 2–3 天 | GAT1–GAT6 | `test:repository` / `test:contracts` 全绿；三套数字口径统一为一套 |
| **B4** 重开门验收 | 3–5 天 | M06′ / M01′ / M03′ / M07′ + arm64 | 逐门留证；不达标则按实测修实现或修订推荐规模，不改阈值宣布通过 |
| **B5** 配置中心 | 5–7 天 | CFG4 表与迁移 + CFG5 解析层 + CFG6 Editor 视图 + CFG7 S3 热切换 | 类 B 配置可在 Web UI 维护并热生效，防变砖三层成立 |
| **B6** 动态运营 | 2–3 天 | CFG8 AI 运营与日志调级 + CFG9 部署文档重写 | 文档与最终模板同构；「0 变量一键启动」可复现 |

### B0 · 阻塞验证

| 序 | 工作项 | 完成口径 |
| :--- | :--- | :--- |
| **DEP0** | 构建 `renderer/Dockerfile`，在容器内以镜像真实用户（当前为 root）走 `wp_renderer` 自己的 `/readyz` 与一次真实截图；**不得由测试脚本代传 `--no-sandbox`** | 得到能/不能启动的确定结论并写入本文；若不能，定稿方案（`--no-sandbox` 或非 root `USER` + 数据卷权限处理），同步 `lite-scale-and-isolation.md` §4 与 M02 边界。v0.2.10 已发布 Lite 曾在 root 下自带浏览器运行，这是先验但**不替代实测** |

### B1 · 交付面收敛

| 序 | 工作项 | 完成口径 |
| :--- | :--- | :--- |
| **DEP1** | 删除 `deploy/compose/compose.yml` 与 `compose.with-deps.yml`；生产保留 `prod.yml` + `runtime-roles.yml`，Lite 保留 `sqlite-lite.yml` | 3 个模板全部可 `docker compose config`；文档同步：`compose.md:3,16-17,50-51,58-60`、`deployment/README.md:15,40-41,154-156,186,200,223,296,337`、`cicd.md:79-83,102-107`、`upgrade-rollback.md:34-35`、`backup-restore.md:27,74`、顶层 `README.md:128` |
| **DEP1a** | 补回 with-deps 承载的两条 runbook 入口：`backup-restore.md` 的 PG 侧演练与 `ai-secret-rotation.md:158-175`「形态 3：内置 PG/Redis 的单机版」 | 两处改为文档内的依赖准备片段（独立 PG/Redis 启动命令），不作为交付模板；改完后按 runbook 实跑一次确认命令可复现 |
| **DEP2** | `Dockerfile.lite` 按 **D-Dep3 双 venv** 合入 Renderer：保留现有 `backend-deps` stage（`uv sync --package backend --frozen --no-dev`）产出 `/app/.venv`；新增 renderer stage 用 `uv sync --package web-presentation-renderer --frozen --no-dev` 产出独立 venv（如 `/app/.venv-renderer`）并 `COPY renderer/wp_renderer`；`PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` + 用 renderer venv 的 CLI 执行 `playwright install --with-deps --only-shell chromium` | 构建成功；压缩体积预期 **635–750 MiB**（v0.2.10 单 venv 形态为 645.4 MiB，双 venv 重复 fastapi/uvicorn/pydantic/httpx 约多 60–100 MiB），> 800 MiB 触发 D-Img1 复审。**把 D-Dep3 的承诺做成门禁而不只是文档**：构建期断言 `/app/.venv/bin/python -c "import playwright"` 必须失败，`backend/app` 全目录无 `import playwright`、`backend/pyproject.toml` 不声明该依赖；进程层守护点为 `config.py:355-382`（遗留 `PLAYWRIGHT_*` 环境变量或 `.env` 键启动即失败）与单测 `backend/tests/unit/test_render_control_plane.py:18-24`。合并的是镜像，不是进程 |
| **DEP3** | `start_lite.sh` 增加第 4 个长期进程，沿用现有 PID 监督、`stop_services` 与 `/etc/hosts` 补 `backend`/`runtime` 别名的技巧 | Renderer 进程必须用**自己 venv 的绝对路径**启动（镜像 `PATH` 指向 `/app/.venv/bin`，例如 `/app/.venv-renderer/bin/uvicorn wp_renderer.main:app --host 127.0.0.1 --port 7400`），并把 `PLAYWRIGHT_BROWSERS_PATH` 传入该进程。4 进程全起，任一退出整容器退出的语义不变；**必须给 Lite 加 tini 作为 PID 1**（`renderer/Dockerfile:61-62` 已有先例）：当前入口是 `sh` 脚本，只 `wait` 自己启动的 3 个 PID，Renderer 死亡后其 Chromium 子进程会被 PID 1 接管但无人 reap 而成僵尸；生命周期演练须检查存活进程、僵尸、临时产物与槽位全部释放 |
| **DEP4** | `compose.sqlite-lite.yml` 收口：删除 renderer 服务、`secrets:` 段与 `depends_on`；`RENDER_WORKERS_CONFIG` 回归镜像默认 `127.0.0.1:7400`（`config.py:135-137`，单容器下才正确）；`RENDER_RUNTIME_NAVIGATION_BASE_URL`/`RENDER_RUNTIME_ASSET_BASE_URL`/`RENDER_PLATFORM_ASSET_BASE_URL` 从 `http://platform-lite:*` 改回环；`RUNTIME_SERVER_ALLOWED_HOSTS` 去掉 `platform-lite,renderer`；healthcheck 补 `127.0.0.1:7400/livez` | 模板 environment 段收敛到 ≤ 10 行；`/readyz` 在无 worker 时 not-ready 的断言（`backend/tests/api/test_health.py:55-68`）在合并形态下仍按预期通过 |
| **DEP5** | `renderer/Dockerfile:45` 从 `playwright install --with-deps chromium` 改为 `--only-shell chromium`，与 DEP2 保持同一参数 | 两侧安装参数一致；renderer 镜像体积下降并记录实测值；真实截图重验归 B4 |

### B2 · 零密钥启动

| 序 | 工作项 | 完成口径 |
| :--- | :--- | :--- |
| **CFG1** | Lite 零密钥启动：按密钥性质分三类处理自动生成，**复用 `RUNTIME_RSA_PRIVATE_KEY` 既有先例**（`config.py:100-109`、`signing_identity.py:161-211` 已实现「ENV → 密钥文件 → `data/` 旧版密钥 → 单实例自动生成」且多副本禁止自动生成），不新造机制 | 三类分别落地：<br>**（a）必须持久化**：`AI_SECRET_ENCRYPTION_KEY` 首启生成落 `/app/backend/data`——它加密库内模型凭证，丢失即不可解密，轮换走已落地的 `rotate_ai_secret_key.py`，生成值不得落入 `_DEFAULT_AI_SECRET_ENCRYPTION_KEYS`；<br>**（b）只需单次启动内一致、无需落盘**：`RUNTIME_BUILD_WORKER_CREDENTIAL` 与 `RENDER_SERVICE_CREDENTIAL` 由入口脚本每次启动生成并导出给同容器子进程（单镜像下 Backend、Runtime、Renderer 同源），**不留静态密钥**；空值会导致构建 Worker 不启动、任务永久 pending，所以必须生成而非留空；<br>**（c）首启播种后不再读取**：`DEFAULT_ADMIN_PASSWORD` 首启生成强随机口令，一次性写入容器日志或改为首登强制改密（二选一并写进用户文档）；<br>统一约束：`backend_multi_instance=true` 时**禁用全部自动生成**（`signing_identity.py:275-284` 要求多副本共享同一把）；卷复用重启后 (a) 类密钥不变；缺失时保持 fail-closed |
| **CFG1a** | **修复占位符拒绝清单的漏网**：`_REJECTED_ADMIN_PASSWORD_PLACEHOLDERS`（`signing_identity.py:41-47`）与 `_REJECTED_BUILD_CREDENTIAL_PLACEHOLDERS`（`:48-53`）都不包含仓库自己模板里用的值 | 实测缺口：`compose.sqlite-lite.yml:79`、`compose.yml:28`、`.env.example:52` 用的 `REPLACE_WITH_STRONG_PASSWORD` 与 `compose.sqlite-lite.yml:34` 用的 `REPLACE_WITH_STRONG_BUILD_CREDENTIAL` **都能通过校验**（清单是精确大小写匹配，只有 `replace-me`/`replace-with-strong-shared-secret`）；代码默认 `Admin123456`（`config.py:78`）同样不在拒绝清单内。也就是说 `_ensure_no_placeholder_secrets` 声称的「单实例/Lite 也禁止照抄 compose 模板直接上线」（`:349`）目前拦不住。补入清单并做大小写/连字符归一，补正负例测试 |
| **CFG2** | 模板瘦身：`.env.example` 96 项 → 类 A 约 9 项 + 生产必需项；移除 4 项 Audience 与 20 余项租约/心跳/轮询/Worker 内存参数（保留在 `AppSettings` 默认值）；`sqlite-lite.yml` environment 段同步 | 分类口径以[环境变量治理](../../developer/architecture/environment-variable-governance.md) §2 为准；被移除项在 `env-vars.md` 保留「隐式调优参数」章节说明，不静默消失 |
| **CFG3** | `runtime.env.example` 密钥边界门禁：断言该文件不得出现 `AI_*`、`DATABASE_URL`、`REDIS_URL`、`*SECRET*`、`*CREDENTIAL*`、`*PASSWORD*` 类变量 | 新增防漂移测试。依据 `compose.runtime-roles.yml:7`：Runtime 三角色只读 `runtime.env`，目的是避免平台密钥进入编译用户代码的容器；瘦身后该边界必须继续成立 |

### B3 · 门禁与文档

| 序 | 工作项 | 完成口径 |
| :--- | :--- | :--- |
| **GAT1** | `tests/contracts/repository/deployment.test.ts:29-41` 的 secrets 断言改为「存在才校验」 | Lite 删除 `secrets:` 段后不再抛错；`:13-27`「每个 git 纳管 Dockerfile 必须同时进 smoke 矩阵与 release 推送 job」保持不变 |
| **GAT2** | 新增 compose 模板镜像可拉取性门禁（`docker manifest inspect`），做成独立测试 + 定时运行，不把网络依赖塞进 `test:repository` | 任一模板引用不可拉取镜像即失败——直接防住「5 个模板全引用拉不到的 renderer 镜像」复发 |
| **GAT3** | `check-image-startup.py` 的 lite 变体：探针补 `127.0.0.1:7400/readyz`，并走 `wp_renderer` 真实启动路径截一张真图（复用 `renderer-image-probe.py` + `verify_renderer_fixture`），不得代传 `--no-sandbox`；同时断言两侧 Dockerfile 的浏览器安装参数一致 | Lite smoke 覆盖「Chromium 能在最终镜像的真实用户与参数下启动」；DEP5 的参数漂移会被门禁挡住。注意现有 `--network none`（`:107-108`）与导航基址的组合需按单容器回环调整 |
| **GAT4** | `scripts/testing/docker_architecture_images.py:26` 与 `docker_architecture_env.py:126,152` 的「独立 renderer 容器」假设按保留形态更新 | 生产演练拓扑不变（仍是独立容器）；Lite 分支按单容器 4 进程校验 |
| **GAT5** | 文档口径统一：三套数字改为一套「两种部署方式 / 三个模板文件」；`deployment/README.md:9` 改为单镜像形态；`lite-scale-and-isolation.md` §2–§5 按该文自己的 §5 要求更新（故障域新增浏览器进程、G1 结论不变、G5 的 Lite 行改写）；用户三篇快速部署恢复「单容器即全部能力」，并统一 registry 口径（`docker.md:12` 阿里云与 `:67` docker.io 不一致） | `pnpm run test:repository` 绿；用户文档与交付模板同构，不再出现「文档说单容器、模板要两容器」 |
| **GAT6** | `cicd.md` / `deployment/README.md` 说明 Lite 不再需要与 renderer tag 对齐、生产角色仍需对齐；`AGENTS.md` §3 的 `deploy/` 描述与顶层 `README.md:128` 仓库结构同步 | 文档、评估、AGENTS.md 三处口径一致；回滚章节不再要求 Lite 用户对齐两个 tag |

### B4 · 重开门验收

| 门 | 重开原因 | 验收口径 |
| :--- | :--- | :--- |
| **M06′** | 模板从 5 个减到 3 个，Lite 拓扑变化 | 按剩余 3 个模板重跑配置/固定镜像版本/manifest 与 digest/权限/可拉取性核对；amd64 与 arm64 各通过真实截图、产物下载与入口加载；外部 Gateway 用 `scripts/contracts/check-gateway-openapi.py` 验证契约 JSON，不以 HTTP 200 或 Backend 直连替代 |
| **M01′** | Lite 单镜像是全新执行拓扑，且 renderer 浏览器参数改为 `--only-shell` | Lite 与 renderer 两侧均覆盖实际入口、有效 PNG、ZIP 下载与加载、凭证拒绝及执行生命周期；官方 Dockerfile 构建成功和健康接口不能代替执行 |
| **M03′** | Lite 容器内新增浏览器进程，2C4G 的 RSS 峰值与 P95 基线基于两容器形态采集 | 按合并形态复核空闲 + 混合负载，对照既有 5 类业务 P95 目标；实测低于目标时按归档收尾计划口径修订 `lite-scale-and-isolation.md` §1 的推荐规模，**不维持名义数字**，也不事后改阈值宣布通过 |
| **M07′** | 数据卷内新增自动生成的 AI Fernet 密钥与渲染凭证 | 备份集内容与密钥绑定关系重新登记；恢复后验证登录、读页、资源下载、**模型凭据可解密**、预览、真实 PNG、ZIP 与入口加载；错误密钥、缺资源、校验和不匹配必须清晰失败 |
| **arm64** | 浏览器层进入 Lite 后 arm64 构建时长与体积未测 | 层体积分解 + QEMU 构建时长 + 一次 arm64 真实截图；结论回填本文与归档调研 |

### B5 · 配置中心（原治理规划 P1）

| 序 | 工作项 | 完成口径 |
| :--- | :--- | :--- |
| **CFG4** | `system_settings` 表 + Alembic 迁移 | 时间列用 `app.db.types.UTCDateTime`、显式取值用 `utc_now()`；PG 与 SQLite 双方言迁移对拍通过（`test:backend:pg-claim`） |
| **CFG5** | 配置解析层：ENV ≻ DB ≻ 代码默认 | **热更新机制要写实**：`get_settings()` 是 `@lru_cache`（`config.py:810`），必须定义显式失效入口与并发安全语义；存储驱动切换要重跑启动期守卫（`signing_identity.py:304-313` 的「多 Backend 必须 S3」）；防变砖三层（保存前 Dry-Run 与连通性实测、启动解析失败降级默认值并告警不进入 Crash-Loop、ENV 紧急否决救砖） |
| **CFG6** | Editor「系统设置」视图：存储 / 常规 / 安全 / AI 运营 / 诊断 | 鉴权复用已有 `require_platform_admin`（`api/dependencies.py:32`），不新建角色体系；`api/routes/system.py:15` 现有的 `app_timezone` 公开端点改为 DB 后端；遵循根 `DESIGN.md` |
| **CFG7** | S3 测试连通性接口 + 驱动进程内热切换 | 「测试连接」实测 AK/SK/Bucket 权限，失败禁止保存；切换后新请求即用新 driver，不重启进程 |

### B6 · 动态运营与文档（原治理规划 P2 剩余）

| 序 | 工作项 | 完成口径 |
| :--- | :--- | :--- |
| **CFG8** | AI 运营配置（全局开关、Models.dev 手动同步触发、图片传输与思考超时）+ 运行时动态日志调级与 HTTP trace 开关 | 供应商级与模型级 `npm` 仍只能通过服务端白名单映射到已实现的 `protocol_key`，Web UI 不得成为动态加载 SDK 的新入口；日志调级用 `logging.getLogger().setLevel()` 即时生效 |
| **CFG9** | 重写快速部署文档（Docker / 群晖 / 飞牛） | 必须在 B1/B3 定稿之后写；突出「0 变量一键启动」，且每条命令实跑可复现 |

---

## 5 停止条件

### 交付面收敛完成（B0–B4）

以下条件同时满足，才可标记为「部署形态收敛完成」：

1. `deploy/compose/` 只剩 3 个模板，分别对应生产的两种规模与 Lite；每个模板引用的镜像在两个 registry 都可匿名拉取，并有 GAT2 门禁守护。
2. Lite 单镜像内 4 个长期进程全部健康，tini 作 PID 1，容器重启不留孤儿 Chromium 与僵尸进程。
3. Lite 零必填变量、零 secret 文件启动后，截图与构建**实际可用**（不是按钮可见或健康接口通过）。
4. M01′/M03′/M06′/M07′ 与 arm64 全部留证；未达标项按实测修实现或修订推荐规模，保持门开放。
5. 三套并存的数量口径收敛为一套，用户文档与交付模板同构。

### 配置治理完成（B5–B6）

6. 类 B 配置全部可在 Web UI 维护并热生效；类 A 精简到约 9 项且在 `env-vars.md` 有明确「必须留在 ENV 的原因」。
7. 防变砖三层有正例与负例证据，其中「非法 DB 值不得导致 Crash-Loop」必须实测。
8. 快速部署文档的每条命令实跑通过。

时间预算到期本身不构成完成。环境暂不可用时登记原因、所需条件和下一动作，保持对应门开放。

---

## 6 风险登记

| ID | 风险 | 处置 |
| :--- | :--- | :--- |
| **R-Dep1** | 容器内 root 无法启动 Chromium，且非 root `USER` 与 `lite-data` 卷权限冲突（首次挂载由 root 创建） | DEP0 先测；两条路都堵则 D-Img1 退回双容器，治理规划的 Lite 最终形态改回带 renderer 服务 + 凭证自动生成，并在用户文档明确 NAS 图形界面路径的能力边界 |
| **R-Dep2** | 删除 `compose.with-deps.yml` 后，PG 侧备份恢复演练与 AI 密钥轮换「形态 3」失去可复现入口（`backup-restore.md:27,74`、`ai-secret-rotation.md:158-175` 都拿它当 `COMPOSE_FILE`） | DEP1a 用文档内依赖准备片段补回并实跑验证；若片段不足以复现，触发 D-Dep1 复审，把 PG/Redis 自备能力以 compose profile 形式挂回 `prod.yml` |
| **R-Dep3** | Lite 与 renderer 两侧浏览器参数再次漂移，导致同一份页面代码在两种形态渲染结果不同 | D-Dep2 统一为 `--only-shell` + GAT3 把参数写进门禁 |
| **R-Dep4** | 下一次 Release 同时是 renderer 首发、自构建 runtime 首发、新目录布局首发与 Lite 合并形态首发，失败面叠加 | 发布验收用明确固定标签与版本清单，不自动移动 `latest`/`sqlite-lite`；先在 pre-release 通道预演，覆盖 amd64 + arm64 |
| **R-Dep5** | D-Dep3 选双 venv 后，Lite 镜像多 60–100 MiB 且多一次 `uv sync`，arm64 在 QEMU 下构建浏览器层与两套依赖的时长可能使 Release 超时 | B4 的 arm64 项记录层体积分解与实际构建时长；超时时先用已有 `cache-scope` 机制缓存浏览器层与 uv 层，仍不达标才重开 D-Dep3，不预先为了体积放弃依赖层隔离承诺 |
| **R-Cfg1** | 配置热更新撞上模块级单例：`@lru_cache` 的 `get_settings()` 被 import 期捕获后，DB 覆盖层改了也不生效 | CFG5 先做一次消费点普查（至少覆盖 `asset_storage_drivers.py:212`、`object_storage_service.py:50`、`auth_cookie.py:15-18`、`main.py:241-242`），按「读时取值 / 启动期绑定」分类后再定失效机制；确实无法热替换的项改归类 A，不硬凑「0 毫秒」承诺 |
| **R-Cfg2** | 自动生成密钥与已落地的 `rotate_ai_secret_key.py` 冲突，或自动生成值被误判为占位符 | CFG1 明确对齐：生成值不得落入 `_DEFAULT_AI_SECRET_ENCRYPTION_KEYS`，轮换脚本能识别卷内密钥来源并写回同一位置；多副本禁用自动生成 |
| **R-Cfg3** | Web UI 成为新的攻击面：类 B 含 S3 凭证与会话策略，写入即生效 | 全部端点走 `require_platform_admin`；secret 类字段只写不读（返回掩码）；保存前 Dry-Run 与连通性实测；变更留 `updated_by`/`updated_at` 审计；ENV 紧急否决权保证改坏后可救砖 |

---

## 7 明确不做的事

1. **不恢复 Backend 进程内 Playwright**（v0.2.10 的旧形态）。`config.py:355-382` 的遗留 `PLAYWRIGHT_*` 启动失败守卫、`backend/tests/unit/test_render_control_plane.py:18-24` 与 AGENTS.md 的「不能在 Backend 进程内自行启动浏览器」必须继续成立；本轮合并的是**镜像**，不是**进程**。
2. **不重新引入 Browserless / CDP 路线**（已作废，见[归档 CDP 方案](../archive/cdp.md)）。
3. **不删除独立 renderer 与 runtime 镜像**：生产两种规模都依赖它们。
4. **不做多副本 Lite**：SQLite 单实例边界不变（Backend 单进程、禁止多容器挂同一 `lite-data` 卷、并发预算固定为 1）。
5. **不在本文给 Lite 规模 SLA**：M03′ 采集前，5–10 人 / 并发 3 仍是目标规模而非承诺。
6. **不改任何队列、租约或任务运行时语义**：`durable_job_lease_service.claim_rows_by_cas` 与 `app/db/` 的方言边界不动。
7. **不把配置中心扩展到工具契约**：AI 工具目录、参数 Schema、调用与返回示例仍是 `tool_specs.py` 派生的系统只读信息，用户只能编辑智能体描述、提示词、工具说明与工具提示词。
8. **不新增 MCP 能力**：`web-presentation-agent-kit` 本期只维护 CLI 接入。

---

## 8 与历史工作项的接续映射

| 归档 IMG 项 | 本轮归属 | 状态差异 |
| :--- | :--- | :--- |
| IMG0 容器内 root 起 Chromium | **DEP0** | 前置条件已解除，仍为最高优先阻塞 |
| IMG1 文档偏差 B1–B6 | 已于 2026-09-29 完成 | 本轮 GAT5 是收敛后的**再一次**口径统一，不是重复纠偏 |
| IMG2/IMG3 发布预演与 ACR 可见性 | **B4 / R-Dep4** | 仍未执行；与 renderer 首发、Lite 合并形态同批发布 |
| IMG4 编排可用性门禁 | **GAT2** | 从「5 个模板全绿」改为「3 个模板全绿」 |
| IMG5 Dockerfile.lite 合入 Renderer | **DEP2** | 浏览器参数按 D-Dep2 统一为 `--only-shell`；归档计划允许「单 venv 或双 venv 均可」，本轮按 D-Dep3 定为**双 venv**，并新增「`/app/.venv` 内 import playwright 必须失败」的构建期断言 |
| IMG6 入口第 4 进程 | **DEP3** | **新增 tini 要求**：归档计划只写「沿用现有 PID 监督」，本轮发现 `sh` 作 PID 1 无法 reap Renderer 的 Chromium 孤儿子进程 |
| IMG7 渲染凭证自动生成 | **CFG1 / CFG1a** | 范围从「渲染凭证」扩到 `_ensure_no_placeholder_secrets` 实际强制的四项（AI Fernet 密钥、管理员初始口令、构建 Worker 凭证、渲染凭证），按是否需持久化分三类处理；明确复用 RSA 私钥既有先例。另拆出 CFG1a：归档计划未覆盖的占位符清单漏网（模板占位值能通过校验） |
| IMG8 编排与默认值收口 | **DEP4** | 增加 healthcheck 补 7400、`RUNTIME_SERVER_ALLOWED_HOSTS` 与导航基址回环化 |
| IMG9 lite 真实渲染验证 | **GAT3** | 增加「两侧安装参数一致」断言 |
| IMG10 Lite 渲染 E2E | **M01′** | 与 M01′ 合并验收，不单独设门 |
| IMG11 arm64 复测 | **B4 arm64** | 口径不变 |
| IMG12 发布与回滚口径 | **GAT6** | 增加 AGENTS.md §3 与顶层 README 结构同步 |

治理规划的 P0/P1/P2 映射：P0 交付项 1/3 → **CFG1 + CFG1a**，P0 交付项 2 → **CFG2 + CFG3**（与 DEP1/DEP4 同批文件，不再单独排期），P1 → **B5（CFG4–CFG7）**，P2 交付项 1/2 → **CFG8**，P2 交付项 3 → **CFG9**。原 P0/P1/P2 的甘特图排期已从治理文档移除，排期只在本文维护。治理文档原 §3.2 的「第二层优雅重启」按 **D-Cfg1 删除**，其 §3.3 记录了决策依据。

---

## 9 执行约束与结果登记

沿用根 [AGENTS.md](../../../AGENTS.md)、[Docker 演练说明](../../developer/testing/docker-architecture-drill.md) 与[已归档收尾计划](../archive/architecture-closeout-plan-2026-10-01.md) §8 的证据要求。Backend 不运行浏览器；Renderer 每 attempt 新建浏览器与 Context；普通 Run 中断不自动续跑但必须终态收敛。

每批先执行改动匹配的最小测试集（`test:backend:unit` / `test:editor:check` / `test:repository` / `test:contracts` 按需），再补真实场景。部署模板、Dockerfile、入口脚本或镜像拓扑变更后，必须重跑 `scripts/contracts/check-image-startup.py` 对应变体与 `test:contracts:gateway`；文档移动至少运行 `pnpm run test:repository` 与 `git diff --check`。

各批实际变更、命令、结果、失败与复测进入 `docs/temp/runs/<date>-<candidate>/`；阶段操作按依赖串行执行，必须创建专属数据库、Redis、卷和回环端口，不复用开发数据。运行记录保存候选与镜像身份、资源和 DB revision、预定目标、独立样本 ID、实际命令与退出码、失败与修复后结果、产物摘要、进程/僵尸/槽位清理证据。密钥、token 和登录态不入库。

阶段结束在本文更新状态；永久契约（环境变量三分类、配置解析优先级、防变砖、安全防线、Lite 故障域与隔离决策）分别维护在[环境变量治理](../../developer/architecture/environment-variable-governance.md)与[Lite 规模与隔离决策](../../developer/deployment/lite-scale-and-isolation.md)，本文不复述其结论，只维护范围、批次、决策与逐门状态。
