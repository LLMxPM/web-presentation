> **归档说明（2026-09-29）**：本文已由新一轮静态评估与计划接替，不再作为现行状态或执行入口。原位置：`docs/temp/plans/deployment-image-consolidation-2026-09-29.md`。历史完成标记、测试结果、发布状态和建议均只代表当时记录；本轮没有重新验证。现行入口：[架构调整收尾工作计划](../plans/architecture-closeout-plan-2026-10-01.md)。

<!-- 文件功能：镜像交付与 Lite 单镜像形态的专项实施计划（规划/未实施，2026-09-29）；隶属现行计划 WS-G，证据见 ../image-delivery-research-2026-09-29.md。 -->
# 部署镜像交付收口与 Lite 单镜像规划（2026-09-29）

> **状态：规划 / 未实施。** 本文不含任何实施记录；落地后按 [`../README.md`](../README.md) 维护约定 2 改状态并同步索引。
> **日期**：2026-09-29。基线 `3818eab`（分支 `dev`）。对照的已发布版本是 `v0.2.10`（2026-09-21 推送镜像）。
> **定位**：现行计划 [`./remaining-work-2026-09-28.md`](./remaining-work-2026-09-28.md) 的**专项子计划**，隶属 **WS-G（Lite / 生产加固）**，具体承接 **G1（故障域）/ G3（密钥治理）/ G5（Renderer 隔离）**。**本文不取代现行计划，不新开第二份现行计划。**
> **证据基座**：[`../image-delivery-research-2026-09-29.md`](./image-delivery-research-2026-09-29.md)（实测层体积、registry 探测、偏差清单 B1–B6、未验证风险）。本文不重复证据，只引用其章节号。
> **编号**：工作项用 **IMG0–IMG12**（Image delivery），决策用 **D-Img1**，风险用 **R-Img\***，避免与既有 `S1–S8` / `Q0–Q12` / `P0–P5` / `M1–M7` / `C0–C4` / `CP1–CP6` / `T0–T4` / `WS-A…H` / `G1–G7` / `D1–D2` / `H1–H4` / `R-*` 冲突。

---

## 0. 一页结论

1. **本文的主轴不是"要不要合并镜像"，而是"交付矩阵从未发布过"**：`renderer` 镜像、自构建 `runtime` 镜像、`deploy/docker/` 新布局全部来自 `75af01e`（2026-09-22），晚于最后一次 Release；`deploy/compose/` 下 5 个模板都引用一个拉不到的镜像（调研 §4、§5-B3）。**镜像形态决策必须排在发布链路修通之后**，否则会拿一个未验证的发布通道去承载一次结构调整。
2. **推荐 D-Img1 = C（双轨）**：lite 镜像内含 Renderer 进程（单容器、面向 NAS/个人/小团队），同时继续发布独立 `web-presentation-renderer` 镜像（面向 `compose.runtime-roles.yml` 等生产角色）。理由见 §2：合并的净体积代价约等于零（调研 §3），而单容器是 NAS 图形界面唯一能表达的形态（调研 §6）。
3. **有一个阻塞级前置验证**：容器内 root + `chromium.launch(headless=True)` 无 `--no-sandbox` 从未被测过（调研 §8.1）。它同时是"合并"与"首次发布 renderer 镜像"的前置，**先测这一项，再决定其余顺序**。
4. **时机**：用户要求"架构完全调整好之后再处理部署问题"。本文按此拆成三档——**S0/S1（止血与发布预演）不触碰架构代码**，若架构收口周期长可提前单独执行；**S2（合并实施）必须等 WS-A/WS-D/WS-G5 的结论**；**S3/S4（门禁与发布）随 S2 或随下一次 Release**。
5. **不做的事见 §7**：不把 Browserless/CDP 路线拉回来（已作废，见 [`../archive/cdp.md`](./cdp.md)），不在本文里重开 Lite 规模承诺（属 WS-D1/WS-G1），不删除独立 renderer 镜像。

---

## 1. 触发时机与前置条件

「架构完全调整好」在现行计划里对应三个可判定的收口点。S2 之前必须全部有结论：

| 前置 | 来源 | 判定口径 | 为什么卡住 S2 |
| :--- | :--- | :--- | :--- |
| **任务运行时契约冻结** | WS-A1/A2 | 9 套领取-租约-心跳方言的契约草案定稿（不必迁完） | 合并后 lite 内同时跑 Backend 与 Renderer 两套任务语义，契约未冻结会把返工面翻倍 |
| **Lite 容量基线（D2）** | WS-D1 | 2C4G 空闲 + 混合负载两轮采集完成，含 RSS/OOM | 「同容器再加一个浏览器进程」的内存结论必须建立在实测之上；现行评估已明确 D2 未过时 Lite 规模只是**目标**不是 SLA |
| **Renderer 隔离决策** | WS-G5 | 容器级隔离 **或** 明确风险接受（二选一并写进治理文档） | 合并会消掉容器边界，G5 若选"容器级隔离"则与 D-Img1=C 直接冲突，必须先定 |
| **构建产物下载覆盖** | WS-D3 | Lite 真实容器内成功产物可下载（`memory://` 计划未覆盖项 2） | 与镜像形态同属 lite 交付面，一起验收可省一轮环境搭建 |

**可提前执行的例外**：S0（IMG1）与 S1（IMG2、IMG4）只改文档、workflow 与编排，不改任何服务代码，因此不受上表约束。当前状态是"5 个 compose 模板全部不可用 + 6 处文档与事实相反"（调研 §5），**若架构收口还要持续数周，建议把 S0/S1 提前独立提交**，理由：它们修的是既成事实的错误陈述，不是架构决策。

---

## 2. 决策点 D-Img1：Lite 镜像形态

> 按 [`../README.md`](../README.md) 维护约定 5，决策必须写清成本影响与复审触发条件。

| 选项 | 内容 | 体积（压缩，推算） | 用户侧步骤 | 隔离 | 主要代价 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A** | lite 内含 Renderer，**不再发布**独立 renderer 镜像 | ~575–650 MiB | 1 镜像 / 1 容器 / 0 密钥文件 | 同容器 | `compose.runtime-roles.yml`（官方生产主路径）失去 renderer 镜像 ⇒ 生产路径被迫也走单容器，**不可接受** |
| **B** | 维持两容器，只修发布与文档 | lite ~350–420 MiB + renderer ~250–350 MiB | 2 镜像 / 2 容器 / 1 手工密钥文件 / 两 tag 对齐 | 容器级 | NAS 图形界面无法表达 secret 文件与双容器编排（调研 §6）⇒ 用户文档必须继续只写单容器，**B4 类偏差会复发** |
| **C（推荐）** | **双轨**：lite 内含 Renderer 进程（单容器）；独立 renderer 镜像继续发布给生产角色 | lite ~575–650 MiB；renderer 另计 | lite：1 镜像 / 1 容器 / 0 密钥文件；生产：不变 | lite 同容器（按 §7.3 第三层风险接受）；生产保持容器级 | lite 与 renderer 的浏览器安装参数需分别维护（`--only-shell` vs 完整 `chromium`），存在漂移风险 ⇒ 由 IMG9 门禁约束 |

**推荐 C 的理由**（证据见调研对应章节）：

- **体积不是代价**：用户今天已经在拉 645.4 MiB 的 lite（自带浏览器），C 之后约 575–650 MiB，**持平甚至更小**（§3）。
- **发布耦合已经存在**：Release 对四个镜像族用同一个 `release_tag`，且文档已要求"两 tag 一起固定、不要只回滚一个"（§5-B2）⇒ C 只是把已有约束在 lite 上取消，不新增耦合。
- **依赖已就绪**：renderer 依赖是 backend 的子集 + `playwright`，同一份 `uv.lock` 已统一解析，`Dockerfile.lite:51` 已 COPY `renderer/pyproject.toml`（§7.1）。
- **配置反而更简单**：`RENDER_WORKERS_CONFIG` 默认值 `127.0.0.1:7400` 在单容器下才正确（§7.4）。
- **进程级边界不被破坏**：Backend venv 仍无 Playwright，`config.py:338-373` 的 fail-closed 校验守的是这一层（§7.3）。

**复审触发条件**（满足任一条即重开 D-Img1）：

1. 合并后 lite 压缩体积 > 800 MiB，或 arm64 构建时长使 Release 超时（调研 §11-6）。
2. IMG0 实测表明容器内 root 无法稳定启动 Chromium，且非 root `USER` 方案与 SQLite 数据卷权限冲突。
3. Lite 需要支持**不可信页面代码 + 多用户**（例如对外开放注册），此时 §8.2 的跨用户越权从"可接受"变为"必须隔离"。
4. Chromium CVE 修复频率导致 lite 全量重拉成为运维投诉（C 会让浏览器安全更新与平台更新绑定）。
5. WS-G5 最终选择"容器级隔离"而非"风险接受"。

---

## 3. 任务分解

### S0 · 事实对齐（止血，不碰架构代码）

| 序 | 工作项 | 完成口径 | 估时 | 依赖 |
| :--- | :--- | :--- | :--- | :--- |
| **IMG0** | **实测容器内 root 启动 Chromium**：构建 `renderer/Dockerfile`，在容器内以 root 走 `wp_renderer` 自己的 `/readyz` + 一次真实截图（不得由测试脚本代传 `--no-sandbox`） | 得到"能/不能启动"的确定结论；若不能，定稿 `--no-sandbox` 还是非 root `USER`，并同步写进 WS-G5 与 P2-ProdHardening | 0.5 天 | 无（**最高优先，阻塞 S2 与 renderer 首发**） |
| **IMG1** | 修正偏差清单 **B1–B6**（调研 §5）：`cicd.md`、`deployment/README.md`、`compose.md`、`renderer/README.md`、用户三篇快速部署 | 文档不再声称未发布的镜像已发布；用户文档明确写出当前已发布 lite 的渲染能力来自哪种形态；`pnpm run test:repository` 绿 | **已完成（2026-09-29）**：B1–B6 已纠偏（renderer/自构建 runtime 标明未发布待首发；lite 双容器表述改为「已发布=单容器自带浏览器 / HEAD 模板=开发中」；模板非开箱即用；用户文档补形态与规模/故障域；B5「两个长期容器」已改；renderer/README 发布承诺改为计划中） |

### S1 · 发布链路预演（首次执行 `build-and-push-services`）

| 序 | 工作项 | 完成口径 | 估时 | 依赖 |
| :--- | :--- | :--- | :--- | :--- |
| **IMG2** | 发布预演：在 pre-release（只推固定版本 tag、不移动 `latest`/`sqlite-lite`）上跑通 `build-and-push-services`，覆盖 amd64+arm64 | renderer 与自构建 runtime 镜像在**两个 registry** 都能匿名拉取；记录构建时长 | 1 天 | IMG0 |
| **IMG3** | ACR 仓库可见性确认与固化：确认命名空间自动创建仓库的默认可见性，必要时显式置公开并写进 `cicd.md` | 调研 §4-3 的 401 变为 200，且结论写进文档（不再是"测出来才知道"） | 0.5 天 | IMG2 |
| **IMG4** | 编排可用性门禁：对 `deploy/compose/` 全部模板做 `docker compose config` + **镜像可拉取性**检查（`docker manifest inspect`），纳入 `test:repository` 或独立 contract 测试 | 任一模板引用不可拉取镜像时门禁失败；5 个模板全绿 | 1 天 | IMG2、IMG3 |

### S2 · Lite 合并实施（**等 §1 前置**）

| 序 | 工作项 | 完成口径 | 估时 | 依赖 |
| :--- | :--- | :--- | :--- | :--- |
| **IMG5** | `Dockerfile.lite` 合入 Renderer：`uv sync` 带上 renderer 包、COPY `renderer/wp_renderer`、`PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`、`playwright install --with-deps --only-shell chromium` | 单 venv 或双 venv 均可，但 **Backend 不得 import playwright**（沿用 `config.py:338-373` 的边界）；构建成功且体积落在 §2 预估区间 | 1 天 | IMG0、WS-G5 |
| **IMG6** | `start_lite.sh` 增加第 4 个长期进程（uvicorn `wp_renderer.main:app` :7400），沿用现有 PID 监督与 `stop_services` 语义 | 4 进程全起、任一退出整容器退出的语义不变；`/etc/hosts` 技巧仍成立；容器重启不留孤儿 Chromium | 0.5–1 天 | IMG5 |
| **IMG7** | 渲染凭证自动生成：入口脚本首次启动生成强随机值并持久化到 `/app/backend/data`，`RENDER_SERVICE_CREDENTIAL_FILE` 指向它 | **不得**退化为镜像内固定常量（P1-Secrets）；卷复用重启后凭证不变；缺失时可 fail-closed | 0.5–1 天 | IMG6，与 WS-G3 合流 |
| **IMG8** | 编排与默认值收口：`compose.sqlite-lite.yml` 删除 renderer 服务与 `secrets:` 段、删除 `depends_on`；`RENDER_WORKERS_CONFIG` 回归镜像默认（`127.0.0.1:7400`）；用户三篇快速部署恢复"单容器即全部能力" | NAS 图形界面流程（`synology.md` / `fnos.md`）无需任何 secret 文件即可完整可用，含截图 | 1 天 | IMG6、IMG7 |

### S3 · 门禁与验证面

| 序 | 工作项 | 完成口径 | 估时 | 依赖 |
| :--- | :--- | :--- | :--- | :--- |
| **IMG9** | `check-image-startup.py` 的 `lite` 变体补**真实渲染验证**：像 `renderer` 分支（:54-63）一样启动一次浏览器，但**走 `wp_renderer` 的真实启动路径**（不得代传 `--no-sandbox`）；同时约束两侧浏览器安装参数不漂移（`--only-shell` vs `chromium`） | lite 镜像 smoke 覆盖"Chromium 能在最终镜像的真实用户与参数下启动"；漂移时门禁失败 | 1 天 | IMG5、IMG6 |
| **IMG10** | Lite 渲染 E2E：在单容器 lite 上跑一次"Editor 发起截图 → PNG 产物落 `lite-data`"的最小链路（复用 `test:render-e2e` 的断言口径，不以按钮可见代替） | 覆盖调研 §11-2 的"成功产物可下载"缺口（与 WS-D3 合并验收） | 1–2 天 | IMG8、IMG9 |
| **IMG11** | arm64 复测：层体积分解 + QEMU 构建时长 + 一次 arm64 真实截图 | 调研 §11-1/§11-6 两项未覆盖项关闭；数据写回本文 §5 | 0.5–1 天 | IMG9 |

### S4 · 发布与回滚

| 序 | 工作项 | 完成口径 | 估时 | 依赖 |
| :--- | :--- | :--- | :--- | :--- |
| **IMG12** | 发布与回滚口径更新：`cicd.md` / `deployment/README.md` 说明 lite 不再需要与 renderer tag 对齐、生产角色仍需对齐；把"lite 单镜像"写进现行评估 §2 的能力表（按调研 §7.3 的**层级**措辞，不写成"Backend 跑浏览器"） | 文档、评估、AGENTS.md 三处口径一致；回滚章节不再要求 lite 用户对齐两个 tag | 0.5–1 天 | IMG8、IMG2 |

**体量合计**：S0 ≈ 1–1.5 天；S1 ≈ 2.5 天；S2 ≈ 3–4 天；S3 ≈ 2.5–4 天；S4 ≈ 0.5–1 天。总计 **约 9.5–13 天**，其中只有 S2/S3 受架构收口约束。

---

## 4. 门禁与验证面（改动清单）

| 门禁 | 现状 | 本文要求 |
| :--- | :--- | :--- |
| `scripts/contracts/check-image-startup.py` | `lite` 变体只探 3 个健康 URL，且 `--network none`（:22-27、:34-41）；只有 `renderer` 分支启动 Chromium，且**自传 `--no-sandbox`**（:54-63） | IMG9：lite 变体走 `wp_renderer` 真实启动路径启动浏览器 |
| `platform-test.yml` 镜像 smoke | 4 个镜像矩阵已存在（:80-101），但**不在 PR 阻塞层**（P0-Gates） | 与 WS-B「架构测试进门禁」合流：镜像 smoke 至少对 lite/renderer 进入阻塞层，否则 IMG9 的守卫可被绕过 |
| `test:repository` | 只查 Markdown 相对链接与代码围栏（`documentation.test.ts:13-41`） | IMG4：追加 compose 模板的镜像可拉取性检查（或新建独立 contract 测试，避免把网络依赖塞进 repository 门禁——**倾向独立测试 + 定时运行**） |
| `test:render-e2e` | 在非 root runner 上跑四服务真实截图 | IMG10：补 lite 单容器形态；不替换现有拓扑 |
| `test:lite:runtime-state-drill` | 有脚本（`package.json:15`）**但不在 CI**（现行评估 P1-Lite） | 不在本文范围，但 IMG10 搭好的 lite 容器环境应顺手让它可被 CI 调用，避免重复搭环境 |

---

## 5. 与现行计划的接口（不重叠声明）

| 现行工作流 | 关系 | 边界 |
| :--- | :--- | :--- |
| **WS-G1**（Lite 故障域评估与承诺文档化） | 本文提供**镜像层**输入：合并故障域已经存在（Runtime build worker 1024 MB old-space 与 Backend 同 cgroup），新增的只是浏览器进程 | **规模承诺仍归 G1/WS-D1**，本文不给 SLA 数字 |
| **WS-G3**（密钥治理） | IMG7 与其合流：自动生成凭证必须与"拒绝弱默认/占位密钥"同时成立 | `.env.example` 弱密钥、compose 内联密钥的清理**仍归 G3** |
| **WS-G5**（Renderer 网络隔离） | IMG0 的结论是 G5 的输入；D-Img1=C 只在 G5 选"风险接受"时成立 | 隔离方案定稿**归 G5**；本文不代为决策 |
| **WS-D1 / D3** | IMG10/IMG11 产出的 RSS、arm64 体积与构建时长回填 D1；产物下载与 D3 合并验收 | 2C4G 两轮基线的采集口径**归 WS-D** |
| **WS-B**（门禁进 PR 阻塞层） | §4 第 2 行依赖 WS-B 的结论 | 门禁层级调整**归 WS-B** |
| **WS-C / P1-VersionSkew** | 双轨后 lite 不再参与跨镜像版本对齐，生产角色仍需兼容矩阵 | 兼容矩阵**归 WS-C** |
| **WS-A** | 仅作为 S2 的时间前置（契约冻结） | 任务运行时统一**归 WS-A**，本文不改任何队列语义 |

---

## 6. 风险登记

| ID | 风险 | 处置 |
| :--- | :--- | :--- |
| **R-Img1** | 容器内 root 无法启动 Chromium，且非 root `USER` 与 `lite-data` 卷权限冲突（首次挂载由 root 创建） | IMG0 先测；若两条路都堵，D-Img1 退回 **B**，并在用户文档明确"NAS 图形界面不支持渲染能力"或提供 `docker run` 专用命令 |
| **R-Img2** | arm64 QEMU 构建浏览器层过慢，导致 Release 超时或被迫放弃 arm64 | IMG11 预演；必要时对 arm64 采用预构建浏览器层缓存（`cache-scope` 已有机制） |
| **R-Img3** | lite 与独立 renderer 两侧浏览器安装参数漂移（`--only-shell` vs `chromium`），导致同一份页面代码在两种形态下渲染结果不同 | IMG9 把参数写进门禁；截图指纹一致性问题另见现行计划 **R-Screenshot**，不在本文重复处置 |
| **R-Img4** | 下一次 Release 同时是 renderer / 自构建 runtime / 新目录布局的"三个首次"，失败面叠加 | IMG2 用 pre-release 通道预演，不移动 `latest` / `sqlite-lite` |

---

## 7. 明确不做的事

1. **不恢复 Backend 进程内 Playwright**（v0.2.10 的旧形态）。`config.py:338-373` 的 fail-closed 校验与 AGENTS.md 的"Backend 不安装 Playwright/Chromium"必须继续成立；本文合并的是**镜像**，不是**进程**。
2. **不重新引入 Browserless / CDP 路线**（已作废，[`../archive/cdp.md`](./cdp.md)）。
3. **不删除独立 renderer 镜像**（`compose.runtime-roles.yml:121` 等生产路径依赖它）。
4. **不在本文给 Lite 规模 SLA**（属 WS-D1/WS-G1；D2 未采集前只能是目标规模）。
5. **不改任何队列、租约或任务运行时语义**（属 WS-A）。
6. **不做多副本 lite**（SQLite 单实例边界；现行评估已明确 Lite 禁止多副本共用 DB 卷）。

---

## 8. 维护约定

1. 本文是**专项子计划**，隶属现行计划 WS-G；单项完成后在 §3 对应表就地勾选并附证据提交，**不新开完成清单**，也不在本文复述现行计划的进度。
2. 出现「实施记录」章节时：同步更新 [`../README.md`](../README.md) 索引状态；整体交付后移入 `archive/` 并加归档横幅，残留项抽回现行计划对应工作流（README 维护约定 2、4）。
3. 本文引用的实测数字全部来自调研文档，**不在本文复制第二份数字**；数字过期时只改调研文档并按其 §10 复核。
4. D-Img1 定案后，须在本文 §2 补「定案日期 + 定案人 + 与 WS-G5 结论的一致性确认」，并按 README 维护约定 5 保留复审触发条件。
