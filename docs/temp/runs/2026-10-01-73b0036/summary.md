# M05 完整旧镜像、迁移与产物组合（2026-10-01）

本轮由 Codex 在本机 Docker Desktop/Linux amd64 执行 M05，实机时间为 2026-10-01 06:57–08:31（Asia/Shanghai）。固定样本的完整入口、迁移中断/应用回滚及公共能力/产物组合已完成，专属项目已清理。基线为 `73b003680827b11a1fae0bbc31207d103bf0f349`，N 候选包含本轮迁移事务与 Renderer HTTP 错误映射补丁；测试时尚未提交，没有推送或发布。N-1 固定 `4c7eee809d19a268e2c919ed5865a62ca388e6df`，从 Git 对象导出完整源码，使用其原始 Dockerfile、`uv.lock`、`pnpm-lock.yaml` 和交付 CMD 构建四种镜像。

## 环境与来源

专属项目 `wp-arch-drill-1594afc0` 使用独立 PostgreSQL 16、Redis 7、数据卷、签名密钥与回环端口，未连接开发数据库/Redis。主拓扑为双 Backend、双 Preview、双 Build、双 Renderer、单 Check、Gateway 与受控模型服务；M05 另建 PG `m05_pg` 和 SQLite `m05.db`，分别运行完整 platform/Lite 入口。三个库使用同一组 Worker，场景串行执行，不是多数据库共享 Worker 的生产承诺。

完整旧镜像使用自己的依赖，已经与当前依赖的旧源码领域探针区分。旧来源与依赖锁见[旧镜像构建身份](./records/n1-images.json)，源码及公共 Kit 摘要见[来源对拍](./records/m05-provenance.json)，本轮修改文件/构建日志摘要见[候选来源](./records/sources.json)；继承的 uv 基镜像 OCI revision 不能代表应用来源。N Runtime 复用 `e82c793` 对应镜像，公开 Kit 和源码未改动。

| 最终 N 镜像 | 实际本地 ID |
| :--- | :--- |
| Lite / 双控制面 | `sha256:b3b7070cfce1bbb8b6cb89f2a57c81de643d6414312c726651bb2cb6c90ba536` |
| platform | `sha256:536c8234c381756502e8fdeecf7c355683b8eb53bc1d232f7cdd7d8c005c9782` |
| Runtime | `sha256:03a6187ff277ec58d7e530d136ec84a10425ce770599f41162e149f84d38bc23` |
| Renderer | `sha256:9adcddc490cfd72a1c1780af988c812a069e27214b2a139f361b5e145cdddb02` |

迁移/业务回滚阶段使用事务修复初版 Lite `9b08e3f…` / platform `acef741…`；最终镜像仅整理了迁移 env 的 import 顺序后重建，已对最终 450 个 Backend Python 文件分别对拍，并补真实两种 N 入口 PNG/ZIP。Renderer 的语义错误修复在迁移演练之后加入，最终 27 个 Renderer/契约源码文件对拍通过；不能把最终镜像 ID 倒填为早期故障/回滚用镜像。

## 迁移、业务与应用回滚

两种数据库均执行完整旧入口自动迁移到 `20260926_0100`，通过真实登录、工作空间/项目/页面/路由与模型配置读写。受控 Chat Completions 只返回正常 `create_entity(page,new)` 工具调用；页面入队、源码校验、远程 Renderer、统一 Task/Batch 与模型自动 deferred 续跑均执行生产代码。成功只创建一页，Task 消费后完整结果清空；另一独立输入阻塞真实检查后通过普通取消 API 终止，Run/Job/Task 均取消。

| 步骤 | PostgreSQL / platform | SQLite / Lite |
| :--- | :--- | :--- |
| 旧完整镜像原始 CMD、自动迁移开启 | 旧 head 与业务通过 | 旧 head 与业务通过 |
| 真实迁移容器中断 | 实际 DROP DDL 被表锁阻塞后 SIGKILL，事务退回旧 head | 实际 ADD DDL 执行后 SIGKILL，修复后列与 revision 一起退回旧 head |
| 前滚到 `20260930_0100` | 完整旧 ORM 查询缺 `lease_generation`，明确失败 | 同样缺列失败 |
| N 迁移器前滚到 `20260930_0300` | 补偿后完整旧 ORM SELECT/UPDATE 通过 | 同样通过 |
| 旧入口自动迁移保持开启 | 未知 revision，真实 CMD 退出码 255 | 同样退出码 255 |
| N 入口关闭自动迁移、保留新 schema | 历史数据读写、页面创建/取消/自动续跑通过 | 同样通过 |
| 回退完整旧应用，关闭旧迁移器 | 保留 head，历史数据读写与创建/取消/自动续跑通过 | 同样通过 |
| N 完整入口关闭迁移但数据库仍为旧 head | 缺 `process_owner`，实际启动退出码 3 | 同样退出码 3 |

旧应用的实际工具写入覆盖了旧 ORM INSERT，独立探针使用完整 SELECT 并对补偿字段 UPDATE 后重读。补偿列默认 0 不恢复删列前历史代次。升级必须排空并停旧实例，再用 N 独立迁移器前滚；本轮没有在删列窗口混跑应用，也没有通过 stamp 或降库规避冲突。

## 实测缺口与修复

1. SQLite 旧迁移引擎使用驱动 legacy 事务，首个 DDL 可在 revision 写入前持久化。真实强杀复现 orphan `process_owner` 与旧 head，重试重复列。新增 `app.db.migrations.configure_migration_transactions`，仅独立 Alembic 引擎显式接管 BEGIN，并声明事务 DDL；历史 revision 未修改，业务 Session 未改变。真实进程在 ADD/DROP DDL 后 `os._exit(91)` 的两项回归修复前失败、修复后通过且可重试至 head。真实 Lite 容器再强杀也通过。历史半迁移负例只从本项目一致快照恢复，不算 M07 生产恢复验收。
2. Renderer 请求 DTO 解码与语义校验分层，`Slot.accept` 抛出的 `RenderContractError` 未在 HTTP 路由映射，无效协议版本返回 500。N 路由现返回 400 `RENDER_CONTRACT_MISMATCH`，保持「已有回执先返回、再校验新接管」顺序；无效画布尺寸与过期票据幂等也通过回归。原完整 N-1 镜像保持不变，仍返回 500，但没有接管或改变槽位代次；记录为历史限制，不算符合新错误映射约定。

旧 Lite 截图还实测到远程 Renderer 不能访问 `127.0.0.1:7373`，Job 三次重试均 `RENDER_INTERNAL_ERROR`。这是旧截图代码使用 Runtime 角色基址、没有使用独立浏览器 navigation 配置的历史限制；当前代码已在上一轮修复。本轮不改旧源码，将旧 Lite 的 `RUNTIME_PREVIEW_BASE_URL` 设为专属网络的 `http://m05_lite:7373` 后定向复测通过。该端口未发布到主机，旧原始 CMD 保留；此配置条件纳入兼容矩阵。

演练自身也修正了入口地址映射、PATCH 方法、Job 终态词、SQL/JSON null 观察、普通取消 API、独立源码避免命中检查缓存，以及 Runtime 替换后的就绪等待。这些是夹具/采集错误，不作为平台缺陷；原始失败与复测分开保留。

## 公共能力与产物

实际页面消费 N-1 已公开的 `DataTable.v1.vue` 和 `usePageSize.v1`，浏览器检查中文表格、1920×1080 尺寸、scoped CSS 和字体，并检查失败请求与页面异常。23 个旧 Kit 公开路径及入口源码逐项一致；实际渲染仅覆盖上述两项样本，不能将指纹对拍等同每项能力渲染通过。

| Backend / Runtime / Renderer | 正常 iframe | 真实截图 | ZIP 与 HTTP 加载 |
| :--- | :--- | :--- | :--- |
| 全 N 主 Gateway | 通过 | Job 8，28949 字节 | Job 7，15233000 字节，通过 |
| N / N / N-1 | 通过 | Job 9，28949 字节 | Job 8，15233002 字节，通过 |
| N / N-1 / N-1 | 503 `RUNTIME_VERSION_UNKNOWN` | Job 11 三次重试失败，无结果 | 独立 Job 9，15232950 字节，加载通过 |
| N / N-1 / N | 同样 503 | Job 12 三次重试失败，无结果 | 独立 Job 10，15232944 字节，加载通过 |
| 全旧 platform，补偿 schema | 通过 | Job 2，28949 字节 | Job 1，15232950 字节，通过 |
| 全旧 Lite，可达 Runtime 基址 | 通过 | Job 2，28949 字节 | Job 1，15232952 字节，通过 |
| 全 N platform 真实 CMD | 通过 | Job 3，28949 字节 | Job 2，15232995 字节，通过 |
| 全 N Lite 真实 CMD | 通过 | Job 3，28949 字节 | Job 2，15232940 字节，通过 |

各 Job ID 按所在数据库区分。两个不支持截图组合使用 20 秒请求期限，最终 Job 为 failed / `RENDER_DEADLINE_EXCEEDED`，RenderRequest 为 expired/cancelled 且 result 为空，占用释放；先前默认期限探针的真实 `RENDER_ASSET_NOT_READY` 与 180 秒等待超时也保留，随后普通取消完成。独立 ZIP 成功不计为预览/截图整链路成功。

六个成功 PNG 的摘要均为 `7ab1bee0b2c6dec4d00e3854452f804413fba2840e3b0db3027310e312cdc158`。完整旧两种入口的原 ZIP，在切回最终 N 应用后从同一 Job 的认证产物接口重新下载，摘要和字节数完全不变，再加载原解压目录，见[旧 platform 产物](./records/m05-platform-old-artifact-on-n.json)与[旧 Lite 产物](./records/m05-lite-old-artifact-on-n.json)。已查看 N 与旧 PNG，标题、中文表格及尺寸正确。

版本组合的正常预览、协议负例、实际 PNG/ZIP、产物 HTTP 加载分别记录，见[组合汇总](./records/m05-combinations.json)和[最终两种 N 入口](./records/m05-current-entries.json)。已通过且候选/页面版本/原产物一致的记录标为复用，不计新执行；旧 Lite 只定向复测其配置与产物，保留此前失败。Runtime 缺发布身份与 Renderer 错误协议属于独立边界。更早的 `4c7eee8` Runtime 没有当前完整版本路由门禁，继续整池排空切换，不承诺任意旧版本同池混跑。

## 验证与后续范围

Backend 迁移/兼容/SQLite/DB 边界最小集合 31 项通过、2 项按原测试条件跳过；Renderer 全部 27 项通过，最终测试夹具隔离调整后的新增三项再次通过；render-contracts 22 项通过。Windows Renderer 单测出现既有 asyncio 子进程 transport 关闭警告，真实 Linux Worker 资源状态另以实际探针核对。

最终 Ruff、Node 语法检查、repository 13 项和 `git diff --check` 通过，实际命令与范围见[测试记录](./records/tests.json)。最终两个 Worker 均 idle、PID 1 为 tini，浏览器/驱动/僵尸与临时文件均为空，见[资源探针](./records/m05-final-workers.json)。三个专属数据库×两个 Worker 的六项只读摘除门禁全部通过；随后只删除本项目容器/卷，均无残留，见[门禁](./records/worker-removal.json)及[清理](./records/cleanup.json)。原开发 PostgreSQL/Redis 仍运行且健康。

没有变更 HTTP DTO、渲染 DTO、Runtime Kit 清单或公开路径，没有新增生成物。没有无理由重复上一轮 85 项 Backend 和 41 项根 contracts。完整 M02、M04 外部交接/Batch 一次消费及构建故障、正式容量、M06 Registry/arm64/最终模板、M07 恢复和 M08 行为/跨仓门继续开放。

原始脱敏 JSON、PNG/ZIP、浏览器截图与测试日志留在 `test-results/docker-architecture/wp-arch-drill-1594afc0/`；镜像构建日志留在 `test-results/docker-architecture-images/`，路径与校验和见[证据清单](./records/evidence-manifest.json)。带凭证的 `.tmp` context/compose 不打印、不入库；大二进制不入库。可重跑命令与前置条件见[演练说明](../../../developer/testing/docker-architecture-drill.md)。本轮完成固定样本的 M05 定向范围，真实已发布迁移范围、任意旧版本兼容与最终发布模板仍单独核对；其它门保持原有开放状态。
