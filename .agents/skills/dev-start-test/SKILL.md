---
name: dev-start-test
description: 管理 web-presentation 主仓本地服务与开发测试：探测复用、按需启停、选择测试、准备 E2E 和执行全量门禁。用于启动/重启/停止服务、查看状态、验证改动或运行测试；维护本地启动、端口及 E2E 排障经验。
---

# 本地开发启动与测试

## 执行边界

- 先探测再操作，只启动任务需要的服务；健康的现有服务直接复用。
- 用户已要求停止/重启，或已授权的 E2E/全量测试需要释放本仓端口时，先 dry-run 核对目标，再执行，无需重复确认。未知归属进程必须取得针对该目标的明确授权后才能 `--force`。
- 不修改 `.env`、不重置开发数据；E2E 数据重置只通过准备入口对 `_e2e` 库执行。
- 按改动选择最小充分测试集。命令语义、补测映射、专项环境、报告路径与汇报要求见[测试矩阵](references/testing-matrix.md)，选择测试时读取对应章节。

## 1. 探测与开发服务

从仓库根目录执行：

```bash
node .agents/skills/dev-start-test/scripts/status.mjs
node .agents/skills/dev-start-test/scripts/status.mjs --json
```

这是只读 HTTP/TCP 探测，不代表端口已空闲。服务 `up` 时复用；`down` 时先检查端口和日志，判断是否需要启动。配置不符时使用 `pnpm run env:check`。开发模式读取根/模块 `.env` 与进程覆盖；E2E 状态使用 `status.mjs --e2e`，与测试入口共享地址解析。

### 首次准备

仅新环境安装依赖；库结构落后时执行迁移，已有管理员不重复播种：

```bash
pnpm install
uv sync --all-packages --all-groups --all-extras
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend python -m app.scripts.seed_admin
```

按实际适配器启动缺失的基础依赖，SQLite 无需 PostgreSQL，`memory://` 无需 Redis。Compose 末尾按需指定 `postgres` 或 `redis`：

```bash
docker compose -f scripts/dev/compose.infra.yml up -d --wait postgres redis
```

### 启动命令

默认端口如下；存在覆盖时使用实际配置。先基础依赖、再 Backend，其余服务按需启动。后台日志写入 `.tmp/dev-logs/`；Windows 后台启动应隐藏窗口。

| 服务 | 命令 | 就绪信号 |
|---|---|---|
| Backend | `uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend` | `/api/auth/me` 返回 200/401 |
| Runtime | `pnpm --dir runtime dev --host 127.0.0.1 --port 7373` | `/__runtime_healthz` 200；构建还需 `/__runtime_readyz` 200 |
| Editor | `pnpm --dir editor dev --host 127.0.0.1 --port 5173` | 首页 200 |
| Renderer | `uv run --project renderer uvicorn wp_renderer.main:app --host 127.0.0.1 --port 7400 --reload --reload-dir renderer` | `/readyz` 200 |

首次启动 Renderer 前安装 Chromium：`uv run --project renderer playwright install chromium`。Node 与 Python 的 Playwright 浏览器分别安装。启动后重新探测并报告服务与地址。默认管理员取根或 Backend `.env`，默认值为 `admin` / `Admin123456`。

显式绑定 `127.0.0.1`，避免 Cookie 站点混用。已有 Editor 若只绑定 `::1`，status 会回退探测并报告可用的 localhost 地址。

### 停止与恢复

```bash
node .agents/skills/dev-start-test/scripts/stop.mjs --dry-run
node .agents/skills/dev-start-test/scripts/stop.mjs --services backend,editor
```

默认停止四类应用服务，不动 PostgreSQL/Redis。仓库路径必须有完整目录边界，父进程追溯只允许已知服务启动器，遇到通用编排进程或终端即停止。任一未知占用会使整批停止被拒绝；进程查询失败不会视作端口空闲。

测试地址有覆盖时，停止或预演均加 `--e2e`。恢复开发环境先停止 E2E 服务，再按上表启动并重新探测。

## 2. E2E 准备与执行

E2E 使用独立 `_e2e` 库、默认 Redis DB 15 和 `AI_TEST_MODE=mock`。**准备会重置并播种测试数据。** 包装器在停服/重置前拒绝非 mock、禁用服务自启或 `TESTING_REUSE_BACKEND=true` 等冲突配置：

```bash
# 只检查；端口占用且未允许停服时会报错
node .agents/skills/dev-start-test/scripts/prepare-e2e.mjs --dry-run
# 先预演并停止可确认归属的本仓服务，再重置数据和启动 E2E 服务
node .agents/skills/dev-start-test/scripts/prepare-e2e.mjs --stop-services
# 首次环境按需追加
node .agents/skills/dev-start-test/scripts/prepare-e2e.mjs --stop-services --start-infra --install-browsers
```

- 预检同时检查 IPv4/IPv6，地址取测试入口的 E2E 覆盖。`--start-infra` 只为不可达且指向本机默认端口的依赖启动对应 Compose 服务；远程/自定义端口不可达时直接报错。
- 不带 `--dry-run` 就会执行准备；结束后保留 E2E 服务，并按相同地址规则校验就绪指纹。
- 每次重置前必须先停 Backend。运行中的 Backend 可能在 `ai_agent_process_owners` 被重置后停止后台执行器。复用已有数据与服务时直接运行 Playwright，不再 prepare。

准备完成后的执行命令：

```bash
pnpm run test:e2e:run
# 全部 project，只执行测试，不再次 prepare
pnpm exec playwright test --config tests/config/playwright.config.ts
# 定向重跑
pnpm exec playwright test --config tests/config/playwright.config.ts --project=ai
```

`test:e2e`、`test:e2e:all`、`test:e2e:regression` 和 `test:render-e2e` 都会再次 prepare；这些一体化入口仅在服务已停止时使用。具体集合与数据纪律见测试矩阵。

## 3. 全量主门禁

```bash
node .agents/skills/dev-start-test/scripts/full-test.mjs --dry-run
node .agents/skills/dev-start-test/scripts/full-test.mjs --stop-services
# 首次环境按需追加 --start-infra --install-browsers
```

包装器共享 E2E 预检并调用 `pnpm run test:all`；除 `--dry-run` 外会真正执行测试。不要先 prepare 再执行全量，准备好的 E2E 服务会占用所需端口；也不要与其它测试并行执行。阶段失败后中止，报告失败阶段与未运行项。

`test:all` 不是全部专项门禁；阶段、未覆盖项和按改动补测规则只在[测试矩阵](references/testing-matrix.md)维护。

## 4. 排障与维护

- 服务异常先看实际地址、端口与日志；端口占用但探针失败时先定位原因，不直接重复启动或要求用户确认。
- E2E 指纹不符或报告“智能体后台执行器正在停止”时，先确认是否经过运行中数据重置，再按第 2 节重建环境；不能据此排除代码回归。
- AI Run 只读诊断：`uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <id> --format summary`。
- 可复用经验、启动/测试脚本变化维护在本技能；`AGENTS.md` 保留触发条件和总体要求。开发者文档保留入口导航，发现冲突示例时同步修正。
- 共享逻辑放 `scripts/lib/`，优先包装根仓已有入口；进程规划与系统执行分离。改脚本后验证语法、dry-run 和对应边界测试。真实停止可使用独立临时监听进程验证，不为验证而停止现有开发服务。

脚本职责：`status.mjs` 探测，`stop.mjs` 停服，`prepare-e2e.mjs` 准备，`full-test.mjs` 执行主门禁；共享库负责地址解析、停服规划、系统进程操作及 E2E 预检。边界测试纳入 `tests/contracts/repository/dev-*.test.ts`，随 `pnpm run test:repository` 执行。
