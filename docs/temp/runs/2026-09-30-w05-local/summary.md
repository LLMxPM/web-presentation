# W05a/b/c 本地实施与验证记录

日期：2026-09-30。最终代码候选：`aab57cd`（`dev`）；本记录后续提交只补证据与计划状态。环境为 Windows 开发机 + Docker Desktop 29.3.1 的 Linux amd64 容器，未作为 2C4G 容量环境或真实多副本测试机。没有推送、发布或在开发/业务数据库执行迁移。

## 1. 分步提交与范围

| 提交 | 产出 |
| :--- | :--- |
| `652c835` | 架构复核、归档、计划与兼容矩阵纠偏 |
| `9afce53` / `563cf7f` | `20260930_0200` 前向恢复旧 Batch ORM 兼容列及导入规范 |
| `99b041d` | `20260930_0300` 实例心跳表、普通 Run 写围栏与独立 CAS 收敛 |
| `7a521ad` | 预览签名版本绑定、版本化 Vite base、HTTP/HMR 拒绝、镜像内置身份及镜像探针 |
| `8128b91` | PostgreSQL 认领合成表使用统一 `UTCDateTime` |
| `aab57cd` | 将 Tailwind 实际扫描的交付源码（包括测试源码）纳入发布 hash |

## 2. 本地验证

每组计数独立记录，存在重叠用例，不合计为唯一测试总数。

| 范围 / 入口 | 结果 | 边界 |
| :--- | :--- | :--- |
| W05a 新旧完整 ORM、缺列负例、迁移往返 | 新增 2 项通过，既有 SQLite 迁移 8 项通过 | 选定 N-1 字段集合的隔离 ORM 回归，未执行旧应用完整页面业务 |
| W05b 存活、启动、DB 边界 | 47 项通过 | 失效/取消收敛、有效 owner 与 Batch 保护、并发单赢家、迟到写拒绝、人工继续绑定 |
| W05b 模型、超时、外部队列、管理器、迁移 | 51 项通过 | 保留普通中断不自动续跑与外部任务交接语义 |
| W05c 正常 Backend 入口、签名与服务换票 | 8 项通过 | 无需人工期望头；原权限/exp 保留；版本探针与代理竞态明确 409 |
| W05c Runtime 身份、真实 Vite、模块、健康、配置 | 52 项通过；hash 输入修正后对应 4 项再次通过 | 真实嵌套 import/CSS/Vite HTTP、跨版 HMR 握手拒绝；独立临时 Vite 服务，不重启开发服务 |
| Runtime `check` / Vite 生产构建 | 通过 | 构建有既有的大 chunk/插件耗时提示；未据此扩大重构 |
| 根仓 `test:contracts` / `test:repository` | 41 项 / 13 项通过 | 文档、部署与模块契约；repository 是 contracts 的子集 |
| `test:contracts:docker-context` / `test:contracts:gateway` | 通过 | 真实 Docker 上下文和 Nginx；OpenAPI 内容、503 透传、原 API 与 SPA |
| PostgreSQL claim + 双库迁移门禁 | 9 项通过、1 项跳过 | 临时 PostgreSQL 16 容器，强制 `P4_POSTGRES_REQUIRED=1`；跳过是选定历史 revision 没有 `thinking_enabled`，不是缺 PG 配置 |

PG 首轮为 4 失败、5 通过、1 跳过：合成表使用无时区 `DateTime`，写入 `utc_now()` 时在播种阶段失败。`8128b91` 改为统一 UTC 类型，复测通过；没有为绕过错误修改生产认领逻辑。测试仅访问自建容器，完成后删除该容器及其临时数据。

W05c 未修改 HTTP DTO、Renderer 契约或 Runtime Kit 公开 import path，没有新增生成类型。Python 新文件及 PG 夹具 Ruff 通过，提交差异检查通过。

可复跑入口（PG 先给隔离容器设置连接串）：

```powershell
uv run --no-sync --project backend pytest -c backend/pyproject.toml backend/tests/integration/test_preview_version_binding.py backend/tests/integration/test_preview_service_token_exchange.py -q
$env:P4_POSTGRES_REQUIRED='1'
uv run --no-sync --project backend pytest -c backend/pyproject.toml backend/tests/integration/test_pg_claim_contention.py backend/tests/integration/test_migration_behavior_contracts.py -q --tb=short -rs
pnpm --filter web-runtime-vue check
pnpm run test:contracts
pnpm run test:contracts:docker-context
pnpm run test:contracts:gateway
```

Runtime 定向 Vitest 使用测试进程 `RUNTIME_ROLE=preview` 避免启动真实领取 Worker；健康用例自行固定 `all`，测试完成后恢复环境。

## 3. 最终镜像证据

本地构建命令为 `docker build -f runtime/Dockerfile -t wp-runtime-w05c:local .` 与 `docker build -f deploy/docker/Dockerfile.lite -t wp-lite-w05c:local .`，源代码为 `aab57cd`。镜像以生产依赖裁剪后的真实入口启动，探针容器 `--network none`，不挂载业务目录、不公开主机端口，结束后删除。

- Runtime 最终镜像构建、健康、实际模块/CSS/Vite、跨版 HTTP 409 与 HMR Upgrade 拒绝通过。原始元数据见 [runtime-image.json](./runtime-image.json)。
- Runtime 镜像另用临时容器删除内置身份文件、清空覆盖值，实际 Vite 启动返回非零并报告“缺少构建身份”；负例通过。
- Lite 最终镜像的真实 Backend/Runtime/Gateway 入口、模块/CSS/Vite、跨版 HTTP 与 HMR 拒绝通过。原始元数据见 [lite-image.json](./lite-image.json)。
- 两种交付形态的 Runtime 发布指纹一致：`1.0.0+sha256-5b25ba86fd930b3ac8d82113d0bd2533b75263deb4cc1a536149702094795db4`。镜像分别按各自 Dockerfile 独立构建，副本/镜像外壳差异未混入 Runtime 发布身份。

原始 `image_id` / `repo_digests` 属于本地构建，不表示远端 registry 已发布或可拉取。此处没有运行 Renderer，也没有获得新的真实截图/构建 ZIP，不能关闭 M01/M06。

```powershell
python scripts/contracts/check-image-startup.py --variant runtime --image wp-runtime-w05c:local --output-dir test-results/images/w05c-final-runtime
python scripts/contracts/check-image-startup.py --variant lite --image wp-lite-w05c:local --output-dir test-results/images/w05c-final-lite
```

## 4. 仍需测试机的场景

固定该候选与最终部署镜像后，按[当时计划（已归档）](../../archive/architecture-improvement-plan-2026-09-29.md)执行：M01 真实截图/构建链路，M04 容器强杀、owner/PID 重用与跨副本保护/一次消费，M05 正常 iframe 同版跨副本/跨版请求、旧应用完整任务业务及真实升级/回滚入口。PG 基础认领/迁移通过不替代这些场景。

M02 权限隔离、M03 受限容量、M06 双架构与发布、M07 完整恢复、M08 UI/权限/跨仓仍按计划保留各自未完成条件。升级继续排空旧 Run/页面任务并停旧业务实例；应用回滚保留前向补偿 schema、关闭旧迁移器；预览池保持同版并排空切换。
