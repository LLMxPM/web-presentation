<!-- 文件功能：e2efe6c..HEAD 多部署落地的代码评审报告（门禁实测 + Critical/Major 复核结论 + 修复顺序）。 -->
# 代码评审：多部署落地 `e2efe6c..HEAD`（2026-09-25）

> **评审范围**：`e2efe6c..HEAD` 共 13 个提交、82 文件、+9678/−817。实质是把 [`plans/runtime-multi-deployment-scaling-plan.md`](./plans/runtime-multi-deployment-scaling-plan.md) 的 **T0-1…T4-3 一次性全部落地**。<br>
> **判断口径**：Critical/Major 均已对照源码逐条复核，不是转述；「声称的能力」与「已实现并可证」严格分开。<br>
> **关联文档**：现行评估 [`architecture-assessment-2026-09-25.md`](./architecture-assessment-2026-09-25.md)；规划正文与任务表见 plan §10。<br>
> **状态**：本文是**落地后评审**，不是规划稿。规划正文状态须与本文一致（见文末实施记录）。

---

## 0. 一页结论

1. **范围兑现度高，但「已落地」不等于「达成门槛」**：角色配置、独立预算、轻量通道、构建持久领取 + attempt 围栏、检查指纹缓存、预览有界缓存、签名密钥环、多副本选址、分角色 Compose——plan §10 任务表上的 T0-1…T4-3 都有对应实现，不是纸面勾选。但逐项核对门槛后有 **5 项只兑现了部分**：T0-2（峰值内存仍在主进程）、T1-2（preview 角色根本没有预算）、T3-3（版本指纹只报告不强制）、T4-2（核对函数是死代码）、T0-1（`workspace` 阶段未计时）。详见 §7 表。
2. **门禁两红一绿**：Backend 全量与 Runtime gate 通过；`test:repository` 与 `test:contracts` 各红一项，**都是 `documentation.test.ts` 断链**，且其中 10 条由本系列自己引入。
3. **三个 Critical 都会产出错误结果**：启动恢复抢走他副本健康租约；租约回收忘作废 `attempt_id` 导致死 attempt 仍能提升产物；预览模块源码可被未鉴权读取（第三条先前已存在，本系列改了这块却没修，还在 `f38a5a4` 把回退扩进 `resolveId`）。
4. **十三个 Major 分三类**：
   - **误导排障方向**（M2、M3）：瞬态 503 被缓存成「代码检查失败」600 秒 → 模型误判自己的源码；永久配置错误被映射成 `RUNTIME_CAPACITY_EXCEEDED` → 呈现成扩容形状的事故。
   - **安全与隔离**（M1、M6、M13）：伪造服务令牌被信任并长期缓存；平台密钥进入编译不可信代码的容器；通配服务令牌抵消 artifact 绑定。
   - **正确性与可用性**（M4、M5、M7、M8、M9、M10、M11、M12）：非幂等重发、槽位永久泄漏、提升非 CAS、无租约续期、succeeded 无产物、指纹不完整、队头阻塞。
5. **做得最扎实的是 `979d039` 签名身份**：多实例强制共享、禁自动生成、kid 冲突 fail-closed、轮换期 JWKS、占位密钥拒绝，9 个测试对准门槛。`claim_job` 的 CAS、鉴权逐次执行、服务令牌不下发浏览器也是真功夫。
6. **顺序门禁被绕过**：plan:270 要求 P3 契约冻结 + D2 写路径基线（评估 序 1–2）先于角色拆分（序 9），而评估 :167 仍记 D2「仍待实测」。T1-1…T1-4 与 T2-3 在该前提未达成时落地。
7. **若只做一件事**：把 `project_build_service.py` 的租约逻辑迁到 `durable_job_lease_service.py` 上——C1、C2、M5、M7、M9 与 owner 可辨识性会一起消失，也止住评估点名的任务模型碎片化主轴。

---

## 1. 门禁实测

| 入口 | 结果 |
| :--- | :--- |
| Backend 全量 | 1021 passed / 9 skipped ✅ |
| Runtime gate（typecheck + 87 tests + build） | ✅ |
| 新增 Backend 单测 / 集成契约 | 76 / 38 passed ✅ |
| `test:repository` | ❌ 红 |
| `test:contracts` | ❌ 红（32 passed / 1 failed） |

两个红都只有一个失败项：`documentation.test.ts`，**46 条断链**。

- 36 条来自 `archive/architecture-assessment-2026-09.md` 历史 `../../../../` 深度错误（本来就红，非本系列引入）。
- **10 条由 `e2efe6c` 新增**：该提交把 `architecture-assessment-2026-09-24.md` 移进 `archive/`，却没改
  - 被移文件内 9 条 `./plans/…`、`./archive/…` 相对链接；
  - `architecture-assessment-sqlite-2026-09.md:3` 的 `../architecture-assessment-2026-09-24.md`。

讽刺点：同一个提交刚给 README 加了维护规则 3 讲这件事。

---

## 2. Critical（都会造成错误结果，不是风格问题）

### C1. 启动恢复会抢走其它副本正在跑的构建

**引入**：`e156630`<br>
**位置**：`main.py:117` → `project_build_service.py:831`

`recover_interrupted_build_jobs_on_startup` 调 `recover_expired_build_jobs(session, force=True)`。`force=True` 时 `:769-770` 丢掉过期谓词，`WHERE` 退化成 `status == "running"`。于是**任何一个 Backend 启动**（扩容、滚动发布、崩溃重启）都会把全局所有 running 构建重置，包括别的副本租约仍有效、正在执行的那些。

**后果**：重复派发 Runtime 构建；健康任务白烧 `attempt_count`。

**仓库自己早有反例**：`asset_render_hint_backfill_job_service.py:232-238`、`page_screenshot_queue_worker.py:161` 都明确只回收过期租约。这直接推翻 `0f89c97` 自己写的 [`multi-backend.md`](../developer/deployment/multi-backend.md)。

**修法**：`force` 仅作用于本进程 `lease_owner` 前缀，或仅单实例生效；多副本只回收 `lease_expires_at` 已过期的任务。其它队列（截图等）若有同类 `force` 逻辑需一并排查。

### C2. 租约过期回收忘了作废 `attempt_id`，死 attempt 仍能提升产物

**引入**：`e156630`<br>
**位置**：`project_build_service.py:797-809`（对照 `release_job_to_pending:318-327`、`assert_attempt_fence:388/:397/:404`）

回收分支清了 `status` / `lease_owner` / `lease_expires_at` / `claimed_at`，**唯独没清 `attempt_id`**。对照 `release_job_to_pending` 是特意清掉的，注释写着「作废 attempt 身份：旧令牌不得再把迟到产物提升为最终结果」。

**后果链**：

1. 回收后任务 `status="pending"`、`lease_owner=None`；
2. 围栏 `:388` 放行 `pending`；
3. `:404` 因 owner 为空**同时跳过 owner 与过期两项检查**；
4. `:397` 的 attempt 又恰好还匹配 →<br>
   **那个本该死掉的 Runtime 迟到上传照样通过围栏并写成最终产物。**

attempt 围栏在回收路径上等于不存在。没有测试断言回收后 `attempt_id is None`。

**同族问题（自查补充）**：`artifact_storage_key` / `artifact_sha256` 等元数据只在 `persist_uploaded_artifact` 写入、`delete_artifact` 清空；`claim_job` / 回 pending / 失败终态都不清。跨 attempt 会残留旧产物指针，failed/pending 任务可能带上次成功产物。

**修法**：回 pending 一律 `attempt_id=None`；fence 在无 `lease_owner` 时直接拒绝；claim 或回收时清空 `artifact_*`。

### C3. 预览模块源码可被未鉴权读取（先前已存在，本系列未修且被 `f38a5a4` 扩大）

**位置**：`runtime-saas-preview.ts:316`、`:271-275`；网关 `web-presentation.conf:104-120`；`internal_runtime.py:76`

```ts
parsed.previewToken || readPreviewTokenCache(previewTokenCache, parsed.artifactId) || ''
```

请求没带票据时，从进程内缓存里**按 artifactId 取别人的票据**去验签（`:322`），验的是缓存里那个人的身份，不是请求者的。

`:271-275`（`f38a5a4` 新增）更进一步，在 `resolveId` 里主动把缓存票据回填到模块 ID 上。

网关侧公开代理 `/@runtime-preview/`，全文件 `auth_request` 出现 **0 次**；`artifact_id` 是 Release 自增整数，可枚举。

**归属要说清**：

- `e2efe6c:267` 已有同样回退（且是无 TTL 的无界 Map），**不是本系列引入**；
- `9c0d58d` 换成 10 分钟 TTL 的有界缓存，**收窄了窗口**；
- `f38a5a4` 把它**扩进了 `resolveId`**。

本系列目标恰恰是 T3-1「预览授权可恢复」，plan 也写明「鉴权仍逐次执行，缓存不能替代权限校验」——**改了这块代码却没修这个洞**。

**修法（很小）**：只认请求里带来的 `previewToken`，绝不从缓存取凭证。

---

## 3. Major

### M1. 客户端伪造的 `x-runtime-service-token` 被无条件信任并以攻击者控制的 TTL 缓存

**引入**：`f38a5a4`<br>
**位置**：`runtime-saas-preview.ts:196` → `runtime-preview-service-token.ts:103-107` → `runtime-preview-cache.ts:85`

- 直接读入站请求头；
- 不做任何验签就写缓存（`resolveTokenWithExpiry:223` 只 base64 解 payload 取 `exp`，注释自己写了「不替代签名校验」）；
- `normalizePositiveInteger(meta.ttlMs, defaultTtlMs)` 只在缺失时兜底、**不封顶** → `exp=now+10y` 能钉 10 年；
- `:98-101` **先查缓存再看请求头**，中毒条目会盖掉 Backend 正常换票路径。

**边界**：需要先持有该 artifact 的有效票据，所以是**共享 artifact 的跨用户 DoS**（A 能把 B 对同一发布的预览打挂到重启），不是提权。

**修法**：网关 `proxy_set_header x-runtime-service-token "";` + 缓存前验签 + TTL 封顶 + 不新鲜的 header 令牌视为缺失并回退换票。

### M2. 瞬态 503 被当成稳定「代码检查失败」缓存 600 秒

**引入**：`b410d94`<br>
**位置**：`code_check_service.py:159-160`（及 `:252-253`、`:351-356`）→ `build_code_check_failed_result:55-80` → `is_transient_check_result:67-89` → `:193-196`

`create_preview_artifact` 抛的 `AppException` 被转成 `{status:"failed", source:"backend"}` 且**没有 `retryable` 键**；`is_transient_check_result` 的四个条件（`status == "unavailable"`、`retryable is True`、`stages.compile`/`stages.render == "unavailable"`、`diagnostics[].source == "infrastructure"`）**一个都不命中** → 入缓存 `DEFAULT_TTL_SECONDS=600`。

而 `put_artifact` 在 Redis 抖动时正是抛 `AppException(503, RUNTIME_STATE_UNAVAILABLE)`。

**后果链**：一次 Redis 抖动 → 那份完全正确的页面源码被缓存成「检查失败」10 分钟 → `validation_result.py:86-94` 拒写 → `page_mutation_executor.py:227-235` 判 job 失败 → **模型被告知自己的源码有问题**。plan §6.1 明令禁止的正是这一条。

**加重情节**：唯一会看 `status_code in {503}` 的 `is_transient_infrastructure_error:92-113` 是**死代码**，除测试外零生产调用者——正确的守卫写出来了，却接在异常层，而真实故障是以 dict 形态到达的。

### M3. 永久性配置错误被误判为「副本满载」，真实错误码被丢弃

**引入**：`fd09322`<br>
**位置**：`runtime_target_router.py:33` `_OVERLOAD_STATUS_CODES = {429, 503}`；Runtime 对配置缺失返回的正是 503：`runtime-build-runner.ts:395,423,599,602`（`JWKS_URL_MISSING`、`BACKEND_API_BASE_URL_MISSING`、`RUNTIME_SERVICE_TOKEN_REQUIRED`）、`runtime-service-auth.ts:32,39`

所有副本共享配置 → 全部「满载」→ `:343-350` 把携带真实错误码的 `last_error` 丢掉，改抛 `RUNTIME_CAPACITY_EXCEEDED`。

该码在 `page_mutation_queue.py:39-46` 被登记为可重试，`pydantic_tools.py:81-83` 还给模型提示「属于容量问题，不要改写页面源码，稍后由平台重试」→ **一个配置 bug 会烧光 3 次 attempt，并呈现成一次扩容形状的事故**。

**修法**：换副本前先区分「容量类 503」与「配置/鉴权类 503」；后者保留原错误码直接失败，不换副本、不进可重试容量码。

### M4. 900 秒非幂等构建 POST 被盲目重发到另一副本

**引入**：`fd09322`<br>
**位置**：`runtime_build_client.py:53-66`；`runtime_target_router.py:246-300`

`POST /builds/project`，路由器对超时 / `RequestError` / 满载 / 5xx 一律 `continue` 换副本，**没有任何方法或幂等性判断**。配合 `runtime_build_request_timeout_seconds = 900.0`，A 已经构建甚至已上传后超时 → 同一构建再 POST 给 B。

plan §5.2 第 5 条原话：「**不能盲目重发可能已上传成功的 POST**」。

**修法**：build 角色对 timeout 不换副本重试（或仅 429/503 换副本）；超时交由租约/重试预算收敛。

### M5. 归档 worker 超时只发 SIGTERM，不升级 SIGKILL → 构建槽位永久泄漏

**引入**：`24b7f29`<br>
**位置**：`runtime-build-worker.ts:1108-1111`（对照同文件 `:548-581` 的正确实现）

`child.kill()` 之后只在 `close` 事件里 resolve。子进程若忽略 SIGTERM，promise 永不落定 → `runtime-build-runner.ts:1118-1122` 的 `finally { rm(tempRoot) }` 不执行（临时工作区泄漏）→ 调度器槽位不释放。

同一个文件 `:548-581` 恰好有正确实现 `waitForChildExitAfterTermination`，注释写着「超出宽限时间后使用 SIGKILL，避免只释放信号量而进程仍运行」。新建的 `runZipArchiveInWorker` 复用 spawn **未获同等保护**。

`RUNTIME_VITE_TASK_CONCURRENCY: "2"`（compose:134,190,219）意味着两次就把 build 角色打瘫，之后永远 429。`runWithRuntimeTaskDeadline` 救不了：它只 abort signal，从不 reject 被 await 的任务。

### M6. 平台密钥泄漏进「编译不可信代码」的容器

**引入**：`e80cf56`<br>
**位置**：`deploy/compose/compose.runtime-roles.yml:24-25`（`x-production-env` → `env_file: ../.env`）、`:128`（runtime-preview）、`:183`（runtime-build）、`:212`（runtime-check）

三个 Runtime 角色都 `<<: *production-env`，把整个 `deploy/.env` 注入容器，其中包含 `DATABASE_URL`、`REDIS_URL`、`AI_SECRET_ENCRYPTION_KEY`、`RUNTIME_RSA_PRIVATE_KEY`（`.env.example:46,47,62,157`）。而 **runtime-build / runtime-check 恰恰是编译用户手写 SFC 的容器**——Vite transform/build 会执行作者代码。

**同一个文件已经给出了正确做法**：`:100` 对 renderer 明确拒绝并写了理由「不复用 \*production-env：Renderer 不需要 DB/Redis/AI 等平台密钥」。三个 Runtime 角色没有沿用这条原则。

**后果**：一次编译期代码执行即可读到数据库/Redis 凭证与 AI 凭证加密密钥；若运维选了 `RUNTIME_RSA_PRIVATE_KEY`（env PEM 形态，`.env.example:150/157` 明确提供该选项），还能读到令牌签名私钥并伪造任意预览/服务/构建令牌——**直接抵消 `979d039` 的签名身份加固**。

**修法**：按 renderer 的方式为三个角色各自声明最小 `environment`；签名私钥只走 `RUNTIME_RSA_PRIVATE_KEY_FILE` 的 secret 挂载且只挂给 Backend。

### M7. 产物提升是 read-then-write，不是 CAS

**引入**：`e156630`<br>
**位置**：`project_build_service.py:463`（复查围栏）→ `:481`（S3 `put_object`）→ `:501`（flush）→ `internal_runtime.py:323,334,353,362`

`internal_runtime.py:323` 载入 job **未加 `with_for_update`**；`:334` 的围栏复查的是**同一个内存对象**；`persist_uploaded_artifact:463` 再查一次仍是同一对象；随后 `:481` 做一次 S3 往返，`:501` flush 出的 UPDATE 只有 `WHERE id=?`，**无 `attempt_id` / `status` 谓词**，最后 `:362` 才提交。

**后果**：两个 attempt 交错时，后提交者获胜而与其有效性无关——正是 plan §5.2 第 3 条禁止的「迟到上传不得覆盖新结果」。竞态窗口覆盖 `archive.read()` + `put_object()` 的整个网络往返。

**注意区分**：`claim_job:270-299` 的领取是**正确的 CAS**（见 §5.2），问题只在**提升**这一段。

**修法**：改为条件 UPDATE —— `... WHERE id=? AND attempt_id=:token_attempt AND status='running'`，并检查 `rowcount`。

### M8. AI Run 停机语义是全局的，与本系列新写的文档相反

**位置**：`backend/app/ai/run_recovery.py:22`（代码，先前已存在）vs `docs/developer/deployment/multi-backend.md:99`（`0f89c97` 新增）

`run_recovery.py:22` 选取所有 `status in ("pending","running","cancelling")` 的 Run，**无 owner / 进程 / 租约过滤**；而 `multi-backend.md:99` 写的是「各副本各自收敛**本进程** Run」。

**后果**：代码是全局收敛。在多 Backend 形态下，启动任意一个副本会把**其它副本正在执行的** AI Run 全判为 `AI_RUN_PROCESS_STOPPED` / `cancelled`。

**归属**：该行代码早于本系列（`74160f6`）。但本系列一边把多 Backend 列为受支持形态（`979d039` 的 `backend_multi_instance`）、一边写下相反的文档承诺，**使原本正确的单实例语义变成了错误承诺**。

**加重**：`test_ai_run_stop_semantics.py:77-91` 用外部 session 播种 Run，恰好把全局行为固化成「预期正确」，掩盖了矛盾。

**修法**：二选一——要么给 Run 加 owner/进程标识并按其过滤收敛，要么把 `multi-backend.md:99` 改成「任一副本启动会全局收敛所有未完成 Run」并说明多副本下的影响。

### M9. 没有租约续期，尽管提交信息声称「租约续期」

**引入**：`e156630`<br>
**位置**：`project_build_service.py` 全文（无 renew）；对照 `durable_job_lease_service.py:92` `renew_running_job_lease`

`project_build_service.py` 中「续期」只出现在 `:43` 的**注释**里（「便于租约续期与结果围栏对齐」），没有任何续期实现。`:146/:497/:544/:589/:628/:655/:689` 写的 `last_heartbeat_at` 全部落在 Redis 运行态（`RuntimeArtifactStore`），**不是数据库租约续期**。共享原语 `renew_running_job_lease` 未被复用（截图队列的 heartbeat 用的就是它）。

**后果**：正确性完全依赖一个**未文档化、未校验**的不变量——`project_build_lease_seconds = 960`（`config.py:119`）> `runtime_build_request_timeout_seconds = 900.0`（`config.py:117`）。只有后者进了 `deploy/.env.example`；把有文档的那个调大到 ≥960，队列循环就会开始偷自己正在执行的构建。

**对比**：`validate_runtime_role_targets`、`validate_shared_identity_deployment` 都有启动期校验器，这个不变量没有。

**修法**：复用 `renew_running_job_lease` 做心跳续期；或退一步，加启动校验器断言 `lease_seconds > build_timeout` 并把两者一起写进 `.env.example`。

### M10. `succeeded` 与产物提升不同事务，且不校验产物是否存在

**引入**：`e156630`<br>
**位置**：`project_build_service.py:604-613`（dispatch 返回即 `complete_job(success=True)`）、`complete_job:344-350`

`complete_job` 的 WHERE 只有 `id / status='running' / lease_owner`，**没有任何 `artifact_storage_key` 守卫**；产物的写入发生在另一个请求、另一个 session（`internal_runtime.py:362` 提交）。两次提交之间崩溃、或上传被围栏 409 拒绝，都会留下 **`succeeded` 但无产物**的任务，而 `/build-artifacts/...` 与下载 URL 已经对外可见。

**测试把它固化成了预期**：`test_multi_replica_coordination.py:106-141` 的 `fake_dispatch` 只累加计数、**从不上传任何产物**，测试却断言 `job.status == "succeeded"`。（该测试对 claim CAS 的部分是有效的：`dispatch_count == 1` 确实证明了单赢家选举。）

**修法**：`complete_job(success=True)` 前置校验 `artifact_storage_key` 非空；或把「提升产物」与「写终态」放进同一事务。

### M11. 检查指纹不完整 → 陈旧结果

**引入**：`b410d94`<br>
**位置**：`code_check_fingerprint.py:77-89`（页面载荷）、`:110-123`（组件载荷）、`:126-200`（依赖身份）、`:221-253`（主题/样式 hash）

plan §6.1 要求指纹覆盖「源码 + 依赖组件版本 + Runtime Kit 版本 + 编译配置 + 会影响结果的主题/样式输入 + 编译器与检查规则版本」。逐项核对后有 **3 处缺口**：

- **(a) 被引用的工作空间资源不在指纹里。** `_resolve_module_graph_identity` 只产出三类 token：`import:{code}:v{n}`、`cv:{code}:v{n}:{content_hash}`、`page:{path}:{sha}`（`:150/:185/:200`）。但被检 artifact 会把引用资源物化进去（`preview_service.py:66` 的 `asset_snapshot_mode="referenced"`、`component_preview_service.py:250`）。**替换或删除被引用资源，缓存仍返回旧的「通过」。**
- **(b) 组件指纹的主题基线是空的。** 组件走 `_build_theme_style_hash(project_id=None)`（`:120`），落到 `:229-235` 的 `theme_key=None, theme_config={}` + 默认画布配置；而真实的组件预览基线是 `workspace.default_theme_key` 经主题库解析（`component_preview_options_service.py:36-38,63`）。**改工作空间默认主题或其色板，不会失效已缓存的组件检查结果。**（字体签名 `:236-252` 是按 `workspace_id` 取的，这部分覆盖正确。）
- **(c) 编译器版本取的是 Backend 镜像的清单，且进程级缓存。** `runtime_kit_version` 来自 `load_runtime_kit_manifest()`，该函数是 `@lru_cache(maxsize=1)`（`backend/app/core/runtime_module_policy.py:38-39`）；**实际执行编译的那个 Runtime 副本的 Vite / 镜像版本不在指纹里**。滚动升级 check 池期间，缓存会继续提供旧编译器产出的结果——正是 plan §7 警告的「`profile.v1` 之类手填标签不足以证明镜像一致」。

**修法**：(a) 把引用资源身份/哈希加入 token 集；(b) 组件指纹解析真实 `default_theme_key` 与色板；(c) 由执行副本回报其 Vite/镜像版本并纳入指纹（可挂在 §4 提到的版本指纹上）。

### M12. 轻量工具与完整编译诊断共用一个准入计数器与冷却

**引入**：`fd09322`<br>
**位置**：`runtime_target_router.py:123`；三个客户端均传 `role="check"`：`runtime_diagnostics_client.py:85`、`runtime_visual_edit_client.py:144`、`runtime_asset_render_hint_client.py:98`

`max_inflight = runtime_build_max_inflight if role == "build" else runtime_check_max_inflight`——**非 build 一律共用 `runtime_check_max_inflight`（默认 16）**。于是 180 秒的完整编译诊断与 10/40 秒的轻量调用（可视化编辑、资源比例测量）挤在同一个计数器里。

**后果**：16 个并发编译就把轻量工具全部打成 `RUNTIME_ADMISSION_FULL`——正是 plan §5.4 / T1-3 要消除的**队头阻塞**；且某个副本的诊断故障会通过冷却连带影响它的轻量工具。Runtime 侧 T1-3 的 lane 分离做对了（`runtime-vite-task-scheduler.ts:1-3`），**Backend 侧的选址与准入没有跟上**。

**修法**：把 `role` 细分为 `check` / `light`，各自独立 `max_inflight` 与冷却。

### M13. 通配服务令牌抵消本系列新增的 artifact 绑定

**位置**：`backend/app/api/routes/internal_runtime.py:126-128`；签发方 `runtime_asset_render_hint_client.py:58`、`runtime_visual_edit_client.py:139`

```python
token_artifact_id = str(claims.get("artifact_id") or "").strip()
if token_artifact_id and token_artifact_id != str(artifact_id):
```

`artifact_id` 为空时**整个校验被跳过**，即一枚不带 `artifact_id` 的 `runtime-artifact-read` 令牌对**任意** artifact 有效（900 秒）。而上面两个客户端签发的正是这种无作用域令牌。

**归属**：先前已存在，但本系列的核心目标之一就是「服务令牌绑定 artifact」（`f38a5a4` 的换票端点、`9c0d58d` 的身份分离），**通配路径使该绑定形同虚设**。

**相关**：换票端点 `internal_runtime.py:160-199` 的唯一凭证是**浏览器可见的预览票据**，无 shared secret / mTLS。今天安全仅因为所有 compose 模板对 backend 用 `expose:` 而非 `ports:`；一旦有人发布该端口，它就变成服务令牌铸造预言机。

**修法**：服务令牌强制要求 `artifact_id`（缺失即 401）；给换票端点加 Runtime↔Backend 共享凭证。

---

## 4. 声称的能力 vs 实际

| # | 声称 | 实际 | 处理 |
| :--- | :--- | :--- | :--- |
| 11 | 分角色多副本拓扑已就绪 | `compose.runtime-roles.yml` 三个角色副本数均为 1；`gateway-upstream.test.ts:47` 只断言 `activeServers.length >= 1`，`:54` 断言第二个 server 是**注释形态** | 补实现或改文档 |
| 12 | 跨副本回归与故障演练 | 整个范围**零 E2E 改动**；plan §11 要求的两预览/两构建检查/两 Renderer 演练不存在 | 补实现或降级宣称 |
| 13 | 文档与规范同步 | AGENTS.md 未更新：Runtime 角色、构建 attempt 围栏、检查指纹缓存、签名密钥环全部缺席，尽管其 §5 要求「Runtime 修改策略发生变化」时同步 | 必须补 AGENTS.md |
| 14 | T1-2「各角色独立执行预算」 | **preview 角色没有调度器**：`vite.config.ts:141-148` 仅在 `surface.projectBuild \|\| surface.checkDiagnostics` 时注册 `runtimeBuildRunner`。于是 `compose:134` 给 runtime-preview 设的 `RUNTIME_VITE_TASK_CONCURRENCY` 是**死配置**，`runtime-role.ts:134-136` 推导出的 `RUNTIME_PREVIEW_VITE_TASK_*`（`.env.example:119-120`、`runtime/README.md:124`）**永不可达**，而 `compose.md:99` 把它们列为 preview 的「对应执行预算」。plan:151 的硬门槛「只拆容器不设约束不视为达成阶段 1」**未过** | 给 preview 面也建调度器（含 HTML/模块转换 lane），或删掉这些变量并改文档 |
| 15 | T0-3「可按角色读出排队年龄、活跃数」 | 承 #14：preview 健康输出里没有 `viteTaskScheduler` 键，该角色读不到排队年龄与活跃数 | 同 #14 |
| 16 | T0-2「归档阶段峰值 RSS 有记录且可控」 | 只对 **child** 采样（`archiveRssBytes`，`runtime-build-runner.ts:1080`）。父进程侧仍有三份整包拷贝：`:1071` `readFile(archivePath)` → `:791` `new Uint8Array(...)` → `:792` `new Blob([...])`。`role=all`（Lite、`compose.prod.yml`、`compose.yml`）下**父进程就是预览宿主**，正是 plan §8 点名的风险 | 父进程侧也采样 RSS；流式上传（长期项） |
| 17 | T3-3「版本固定或排空」 | `runtime-health.ts:82-87` 报告 `runtime_kit_version` / `build_id`，但 `runtime-saas-preview.ts`、`runtime-preview.ts`、nginx 配置**无任何路径消费或强制**它。排空只是 `compose.md:129-134` 的手工流程且**没有上界**：浏览器 HMR websocket 在 `proxy_read_timeout 3600s` 下长期不断，「在途」永不排空。第二个副本一旦取消注释，HTML 来自 v1、模块/CSS 来自 v2 而无人察觉 | 把指纹接入子请求校验，不匹配即拒绝 |
| 18 | T4-2「摘除旧实例前核对未释放 attempt」 | `0896cc7` 的 `list_unreleased_attempts_for_worker` / `can_safely_remove_worker`（`rendering/repository.py:243-265`）**除内部互调外只有测试调用者**，无路由、脚本或协调器接入 = **死代码**。谓词本身正确（跨 epoch，镜像 `:227-240`），但没有任何可执行东西在保证这件事；`compose.md:142` 只有散文描述 | 接入运维脚本或控制面端点 |
| 19 | T0-1 六阶段计时 | `workspace` 阶段**未计时**：`runtime-build-runner.ts:981` `createDisposableRuntimeWorkspace`（全量 `src` 拷贝 + node_modules 软链）在任何计时器之前执行，`:994` 的 `workspace.created` 无 `durationMs`。另外 `archive` 记的是 **child 自报**的 `durationMs`（`:1076`），不含 spawn/写脚本/父进程 `readFile`，与其它阶段的墙钟口径不一致 | 补 `workspace` 墙钟；统一 archive 口径 |
| 20 | 容量观测覆盖「超时率」（plan §5.4） | `RuntimeWorkloadCounters`（`runtime-capacity.ts:11-16`）只有 `calls/totalDurationMs/lastDurationMs/maxDurationMs`，**无失败/超时字段**；`recordRuntimeWorkload` 的 7 个调用点全在成功路径（`build-runner.ts:360,522`、`saas-preview.ts:235,356,366`、`visual-edit.ts:88`、`measurer.ts:86`）。每个 429/504/OOM 在容量输出里都不可见 | 加 error/timeout 计数并在 catch 路径记录 |

### 4.1 其它工程债

- **巨石文件继续长大**（AGENTS.md §1 有行数约束）：`runtime-saas-preview.ts` 1252→1477、`runtime-build-worker.ts` 1021→1231、`project_build_service.py` 495→875。
- **测试同义反复**（证不了宣称）：
  - `test_multi_replica_coordination.py` 无第二进程、无 PG、无产物提交，`fake_dispatch` 从不上传却断言 `succeeded`，证明不了「多实例不重复提交产物」；
  - `runtime-saas-preview.test.ts:25` 整个 mock 掉 `jose`，`jwtVerify` 无论参数都 resolve；
  - `CodeCheckFingerprintBuilder` 零覆盖，「任一组件变化即失效」测的是手写 payload；
  - 把 `lane.active -= 1` 从 `finally` 移进 `try`（即每个抛错任务泄漏一个槽位）没有任何测试能抓到。
- **配置/文档漂移**：`PROJECT_BUILD_*` 5 项未进 `deploy/.env.example` 与 `env-vars.md`（`grep PROJECT_BUILD deploy/.env.example` 命中 0）；`RUNTIME_BUILD_ID` 文档/compose 有、两份 `.env.example` 无。完整清单见 §4.2。

### 4.2 Minor 与工程细节

**安全/健壮性**

- **预览 HTML 不设 `Cache-Control: no-store`**：`sendHtml`（`runtime-saas-preview.ts:1378-1382`）只设 `Content-Type`，而相邻的 `sendCss:1390-1392` 与 `:1161/:1179/:1408` 都设了 `no-store`。HTML 正文内嵌 bearer 票据与 `?token=` 样式表链接，缺 `no-store` 与 `Referrer-Policy`。
- **票据校验欠规格**：`runtime-saas-preview.ts:664-669` 的 `jwtVerify(token, jwks, { audience })` **只有 audience**——无 `algorithms` allowlist、无 `issuer`、无 `maxTokenAge`、无 `clockTolerance`，且**不要求 `exp` 存在**（jose 对无 `exp` 的令牌视为永不过期）。`jti` 在 `:677` 被强制要求存在，但全文只在 `:87`（类型声明）与 `:677` 出现——**从不使用**，因此无重放检测、无撤销路径，而默认 TTL 是 3600 秒。`alg:none` / HS256 混淆被 jose 的 JWKS 键类型与 Backend 侧 `algorithms=["RS256"]`（`token_service.py:90`）挡住，所以这是纵深防御 + plan §5.1 未兑现的文档要求，不是开放漏洞。
- **`/__runtime_healthz` 未鉴权，且浏览器不可达是偶然的**：`runtime-health.ts:41-46` 无任何校验。它今天不可从浏览器访问，仅仅依赖插件中间件恰好早于 Vite `baseMiddleware` 注册；`deploy/.env.example:11-12` 把 `RUNTIME_SERVER_BASE_PATH=/` 列为受支持取值，一旦 base 为 `/`，`baseMiddleware` 不安装，pid / RSS / role / build_id / 各角色预算就变成全网可读。无测试钉住这一点。
- **陈旧 manifest 可活过已删除的 artifact**：`/__preview` 用 `Promise.all` 并发跑 manifest 与 config-bundle（`runtime-saas-preview.ts:217-220`），config-bundle 的 404 到不了 `invalidateArtifactCaches`，缓存的 manifest 最多再服务 10 分钟。
- **换票无 in-flight 合并**：`runtime-preview-service-token.ts:98-116` 与 `runtime-saas-preview.ts:1000-1023` 都没有 pending promise 合并。冷副本/刚排空副本上一次页面加载会并发打出 N 个 `POST /internal/runtime/preview-service-token` + N 个 manifest 请求（N = 模块数，轻易 30–60）——正是 T3-1/T3-3 针对的多副本重启场景。
- **`redactJwtForLog` 反而毁掉诊断信息**：`runtime-preview-service-token.ts:268` 把任何非 JWT 且长于 16 字符的消息截到 8 字符（`模块未包含在发布白名单中：src/views/X.vue` → `模块未包含在发布白…`）。而且它是多余的：`runtime-logger.ts:124-131` 已在 sink 层脱敏 `?ctx=`、`Bearer …` 与 JWT 三元组（含堆栈，`:72-77`）。
- **容器 OOM 被误报**：`runtime-build-worker.ts:866-872` 的 `isRuntimeBuildWorkerOomFailure` 只认 `exitCode === 134` 与 V8 stderr 字样。cgroup OOM-kill 给的是 `code=null, signal=SIGKILL` → 落到通用 `RUNTIME_BUILD_WORKER_FAILED`（`:1166-1171`）。而这恰是**更可能**的模式：`--max-old-space-size` 约束不了 child 读入的 `Uint8Array` 载荷（`:783` 把每个 dist 文件读进内存）。plan §8 要求监控 RSS/OOM。
- **轻量通道超时只释放槽位，不取消工作**：`runtime-light-tool-channel.ts:56-70` 用 `Promise.race` 拒绝后，`execute` 的 `finally` 递减 `active`，但 `run()` **从不取消**。Backend 在 504 后重试会堆积无上限的孤儿 mermaid/jsdom 工作，`RUNTIME_LIGHT_TOOL_CONCURRENCY` 失效。更糟：`analyzeVisualEditRequest` 与 `mermaid.render` 在主进程内是 CPU 密集型，阻塞期间 `setTimeout` **根本无法触发**，10 秒上限在最需要它的时候不可执行。
- **`readJsonBody` 无字节上限**：`runtime-asset-render-hint-measurer.ts:377-391`，对照 `runtime-visual-edit.ts:107-120` 是有的。
- **轻量通道未在关闭时清理**：visual-edit / measurer 都没有 `httpServer.once('close')`，对照 `runtime-build-runner.ts:243-248` 是有的。

**Backend 侧**

- **归档压缩级别无实测机制**：`normalizeArchiveCompressionLevel(12)` 静默返回 6（`runtime-build-worker.ts:707-717`）而不是启动期报错；`zipSync(..., { level })`（`:795`）对所有条目用同一级别，把已压缩的 png/woff2 再 deflate 一遍；**没有记录实际压缩比**，所以 plan「压缩级别按实测产物设定」没有落地机制。
- **`RUNTIME_ARCHIVE_WORKER_TIMEOUT_MS` 是死配置**：`DEFAULT_ARCHIVE_WORKER_TIMEOUT_MS=120000`（`:12,723-729`）永不生效——唯一调用方传了显式 `timeoutMs`（`runtime-build-runner.ts:1068`），而 `normalizePositiveInteger` 优先显式值。归档实际消耗的是 600 秒构建 deadline 的余量，不是 120 秒预算。
- **每请求构造两个 service 实例**：`internal_runtime.py:334` 与 `:352` 各 `ProjectBuildService(session)` 一次，每个都新铸一个随机 `lease_owner`。
- **`claim_job:268` 在方法中途 commit 调用方的 session**——对未来任何 route 作用域的调用者都是陷阱。
- **失败终态残留租约字段**：`complete_job:344-350` 只在成功时清 `lease_expires_at`；`:811-821` 的 failed 分支保留 `lease_owner` / `claimed_at`，终态行上留着陈旧 owner。
- **`BUILD_LEASE_EXPIRED` 在默认配置下不可达**：构建令牌 TTL 900 秒（`token_service.py`）< 租约 960 秒，所以活着的 attempt 永远先因令牌过期而 401。测试只能靠手改数据库行触发（`test_project_build_job_lease.py:342`）。
- **恢复循环逐条 UPDATE**：`recover_expired_build_jobs:788-822` 每秒轮询时对每个候选发一条 UPDATE，未用 `durable_job_lease_service.recover_expired_running_jobs` 的批量形式（后者是为 SQLite 写锁特意批量的）。
- **`attempt_id` 对外暴露且创建期即铸造**：`schemas/project_build.py:41-44` 公开 `attempt_id`；`create_build_job:126` 在创建时就铸了一个 attempt 身份，而围栏在 `pending` 状态下是承认它的。
- **`lease_owner` 缺主机/进程标识**：`project_build_service.py:44` 用 `f"build-worker:{uuid4().hex}"`，而共享的 `build_durable_worker_id()` 给的是 `hostname:pid:uuid`。在本系列主打的多副本拓扑里，**无法从 owner 字符串判断租约在哪个副本上**。
- **检查缓存容量/TTL 是模块常量**：`code_check_result_cache.py:22-23`，`get_code_check_result_cache()`（`:256-262`）永远用默认值，没有 `AppSettings` 字段也没有 `.env.example` 条目——尽管注释写着「调用方可按部署规模覆盖」。
- **检查缓存指标无出口**：hits/misses/coalesced/evictions/expired/skipped_transient/hit_rate 都统计正确，但只每 50 次查询 `logger.info` 一次（`:239-250`），`snapshot_metrics` 没有接到任何 health/metrics 端点。
- **冷却只是重排不是排除**：`runtime_target_router.py:75-77`，所有目标都冷却时每个请求仍要先在死副本上付满一次超时（build 场景最坏 N × 900 秒）；failover 全程**没有总 deadline**。
- **轮转索引在准入之前推进**：`ordered_candidates:71-72` 先动 round-robin 指针再做 `admission`（`:231`），准入拒绝会使轮转偏斜。
- **缓存结果携带已删除的 `artifact_id`**：`code_check_service.py:503-512`、`component_validation_service.py:126-133`；今天只被日志消费（`page_mutation_executor.py:220,368`），但是个活雷。`_code_check_cache`（`:429`）还把内部标记泄漏进 AI 工具结果。
- **事件循环延迟直方图每 60 秒 `reset()`**：`runtime-capacity.ts:78-80`，探针若正好落在 reset 之后会读到接近 0 的 mean/max，掩盖真实阻塞。容器内存**上限**从不导出，plan §5.4 的「进程与容器内存」无法对照。`stopRuntimeEventLoopLagMonitor` 未接到 server close。
- **`RUNTIME_VITE_DIAGNOSTICS_WEIGHT` 是 no-op 却仍被设置**：`compose.runtime-roles.yml:222` 设了 `3`，而 `runtime-vite-task-scheduler.ts:1-3` 已改为各类别独立 lane，权重只是兼容字段。
- **诊断工作区池的 waiter 数组无界**：`runtime-diagnostics-workspace-pool.ts:153-164` 推入无 deadline 关联的 `waiters`；安全性只靠「池大小 == diagnostics lane 并发」这个由 `runtime-build-runner.ts:228` 维持、且无测试的不变量。
- **`runtime-preview-cache` 只按条数不按字节设界**：200 条 Tailwind CSS 字符串可达数十 MB；`size` getter 有副作用（`:114-117`）。
- **nginx 无 upstream `keepalive`**，非 WS 请求走 `Connection: close` → 每个模块请求新建 TCP 连接；单副本下 `proxy_next_upstream_tries 2` 是空操作。

**文档漂移（除 §4 表 #13 外）**

- **`docs/developer/backend/resource-queues.md:46` 仍在描述已废除的模型**：「Runtime 诊断与正式构建**共享调度槽**，默认按诊断:正式构建 `3:1` 加权领取」——与 `runtime-vite-task-scheduler.ts:1-3`（各类别独立并发与队列）直接矛盾，也违反 T1-2 门槛「单靠权重参数不再作为唯一保障」。全文未提轻量通道与分角色预算。该文件最后由 `e2efe6c` 触碰，本系列未更新。
- **`docs/developer/deployment/compose.md:112` 过期且照做会出错**：「模板可先于角色逻辑部署；在角色路由契约完成前，Backend 的 `RUNTIME_BASE_URL` 仍指向 `runtime-preview`，构建与源码检查内部目标按发布顺序逐项切换」。T1-1 已在 `f38a5a4` 落地、模板也已设好三个目标（`compose.runtime-roles.yml:58-62`）；**照这段文档做会把 build/check 路由到 preview 实例**，那里端点已注销 → 请求落回 Vite（`runtime-build-runner.ts:270`）→ Backend 收到 HTML/404 而不是结构化错误。Backend 侧的守卫只 **warn**，且仅在显式设了 `RUNTIME_PREVIEW_BASE_URL` 时才 warn（`backend/app/core/config.py:764-790`）。
- **`docs/temp/README.md:17` 与 plan:3 仍写「未实施」**：正文说「角色拆分、预览授权可恢复、构建持久领取均未开始」，而其后 11 个提交把它们全做了。违反 README 自订规则 2（`e2efe6c` 自己加的），规则 4 要求的「实施记录」也不存在。
- **顺序门禁**：plan:270 与评估 §7.3 序 1–2 / 序 9 的先后关系未被遵守（见 §0.6）。

**env / 文档漂移清单**

| 变量 | 读取处 | `runtime/.env.example` | `deploy/.env.example` | `env-vars.md` | 备注 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `RUNTIME_ARCHIVE_COMPRESSION_LEVEL` | build-worker.ts:710 | ✗ | ✗ | ✗ | 默认 6 |
| `RUNTIME_ARCHIVE_WORKER_TIMEOUT_MS` | build-worker.ts:726 | ✗ | ✗ | ✗ | 默认 120000，且**已死**（见上） |
| `RUNTIME_BUILD_ID` | runtime-health.ts:85 | ✗ | ✗ | ✓ :97 | 默认 `''` |
| `RUNTIME_SERVER_ALLOWED_HOSTS` | vite.config.ts:41 | ✗ | ✗ | ✗ | 先前已存在 |
| `RUNTIME_LIGHT_TOOL_*`（4 项） | runtime-role.ts:122-130 | ✓ | ✓ | ✗（仅 :78 指针） | 默认 2/32/5000/10000 |
| `RUNTIME_VITE_TASK_*`（preview 上） | — | ✓ | ✓ | ✓ :78 | **对 preview 是 no-op**（#14） |
| `RUNTIME_PREVIEW_VITE_TASK_*` | runtime-role.ts:135 | ✓ | ✓ :119-120 | ✗ | **永不可达**（#14） |
| `RUNTIME_CHECK_MAX_INFLIGHT` | config.py:97 | n/a | ✓ =16 | ✓ :95 | 16 小于单副本 2+32（`compose.md:118` 的公式） |
| `RUNTIME_VITE_DIAGNOSTICS_WEIGHT` | scheduler.ts:131 | ✓ | ✓ | ✗ | 默认 3，no-op |
| `PROJECT_BUILD_*`（5 项） | config.py:119-123 | n/a | ✗ | ✗ | 含 M9 依赖的 960 秒租约 |
| `RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB` | build-worker.ts | ✓ 1024 | ✓ 2048 | ✗ | 两份 example 取值不同，代码默认 1024；`env-vars.md` 两个都没写 |

---

### 4.3 顺序与架构层面

- **又手写了一套租约方言。** `backend/app/services/durable_job_lease_service.py` 已提供原子认领（`claim_pending_jobs`）、续期（`renew_running_job_lease:92`）、owner 流转、过期恢复（`recover_expired_running_jobs`）与 `build_durable_worker_id()`，**7 个服务在用**（component/image/page mutation queue、page_mutation_executor、asset_render_hint_backfill、mutation_job_service、page_screenshot_job_service）；`project_build_service.py` **一行都没引**。评估 §7.3 序 3 的原话是「**直接套用已有 external 任务模式**」，而评估的头号结论正是任务模型碎片化（9 套领取-租约-心跳-恢复-错误码方言）为剩余主轴。本系列使其成为第 10 套。C1、C2、M7、M9、M10 与 owner 可辨识性问题都源于此。
- **plan 的阶段门禁与验收证据缺位。** plan §9「每一阶段完成后才能扩大其部署承诺」、§11 的多副本/故障演练矩阵、§5.1「上述改造完成前 `runtime-preview` 保持单副本」——代码全部先行落地，而验收证据（跨副本 E2E、故障演练、真实网关回归）一项都没有。plan:320 自己写了「规划文档本身不代表这些门禁已经通过」，本系列正处于这个状态。

---

## 5. 做得好的部分

这些不是客套，是逐条核过的硬优点：

1. **`979d039` 是整批最扎实的提交**：多实例下强制显式共享私钥、禁止自动生成、kid 冲突启动即失败、JWKS 同时公布新旧钥、`_ensure_shared_secret_material` 拒占位值、`memory://` 与本地对象存储 fail-closed，9 个测试对准门槛；`multi-backend.md` 的轮换步骤连 TTL 上限（预览 3600s / 构建诊断 900s、建议保留旧钥 1 小时）都写清了。
2. **`claim_job:270-299` 是真正的 CAS**：谓词在 `UPDATE` 的 `WHERE` 里重复、`attempt_count + 1` 在 SQL 侧、`rowcount` 定胜负、候选读先提交以免占着 SQLite 读事务；两种引擎都正确。时间处理干净（`UTCDateTime` + aware `utc_now()`，无 naive/aware 混用），重试预算有 `deadline_at` 双重封顶，按 attempt 的不可变对象键设计正确。
3. **鉴权确实逐次执行**：`external/validate.py:31-46`、`ai/tools/code_check.py:34-38` 都在缓存查询之前跑完 scope + 归属校验，`code_check_service.py:125-126` 还有自己的 workspace 守卫。异常一律不入缓存。in-flight 合并在成功和异常两条路径都真清理，且有测试。
4. **服务令牌可证明不下发浏览器**：snapdom 代理只把它转发给资源源站；日志在 sink 层脱敏（含 Vite 自己的 logger 和堆栈）；JWKS/Backend URL 缺失一律 503 fail-closed；`PreviewBoundedCache` 是真 LRU+TTL。
5. **角色门禁是真注销而非文档**（`vite.config.ts:124-163`），lanes 是各自独立对象；事件循环延迟用 `monitorEventLoopDelay`、内存用 `process.memoryUsage()`，不是自证式的 `setInterval` 差值。
6. **`/internal/` 未经公开网关暴露**：网关 location 列表不含 `/internal`，`location /` 走静态资源 → 404。已单独核过。

---

## 6. 建议处理顺序

| 优先 | 项 | 理由 |
| :--- | :--- | :--- |
| 1 | **C1、C2、C3** | 都会产出错误结果；C3 是跨租户读源码 |
| 2 | **M6、M13** | 密钥进入执行不可信代码的容器；通配令牌使 artifact 绑定形同虚设——两者都抵消本系列自己的安全加固 |
| 3 | **M2、M3** | 一个让模型误判自己的代码，一个把配置事故伪装成容量事故，都会误导排障方向 |
| 4 | **M5、M7、M10、M9** | 槽位永久泄漏 / 提升非 CAS / succeeded 无产物 / 无续期——都是「结果不可信」一类 |
| 5 | **M1、M4、M11、M12、M8** | DoS / 双跑构建 / 陈旧检查结果 / 队头阻塞 / 文档与代码相反 |
| 6 | 修 `test:repository` 的 10 条新断链，让门禁转绿 | 同一提交自己引入的债，且 `test:contracts` 也一并红 |
| 7 | **#14、#16、#17、#18、#19、#20** | 「声称已落地但门槛未过」的六项：要么补实现，要么把 plan/文档的宣称降级 |
| 8 | 按 README 规则 2/4 给 plan 补实施记录、把「未实施」改掉；补 AGENTS.md（#13）；修 `resource-queues.md:46`、`compose.md:112` | 文档与实现一致；`compose.md:112` 照做会真的路由错 |
| 9 | §4.2 Minor 清单 | 可批量处理；其中 healthz、`sendHtml` 缺 `no-store`、票据校验欠规格三项建议并入优先级 2 一起修 |

**如果只想做一件事**：把 `project_build_service.py` 的租约逻辑迁到 `durable_job_lease_service.py` 上——C1、C2、M7、M9、M10 和 owner 可辨识性问题会一起消失，也止住 [`architecture-assessment-2026-09-25.md`](./architecture-assessment-2026-09-25.md) 点名的**任务模型碎片化**主轴。

**如果只想做两件**：再加一项——把 `runtime_target_router.py` 的 503 分成「容量类」与「配置/鉴权类」，并给 `role` 加 `light`。M3 与 M12 会一起消失，排障信号也会恢复真实。

---

## 7. 与 plan 任务表的对应

「代码已落地」与「plan 门槛已达成」分列——两者不等价是本批的主要特征。

| 任务 | 落地提交（主） | 代码 | 门槛 | 评审结论 |
| :--- | :--- | :---: | :---: | :--- |
| T0-1 六阶段指标 | `24b7f29` | ✅ | ⚠️ | `workspace` 阶段未计时、`archive` 口径不一致（#19）；无失败/超时计数（#20） |
| T0-2 归档子进程化 | `24b7f29` | ✅ | ⚠️ | CPU 已移出，**峰值内存没有**（#16）；**M5** 超时不升级 SIGKILL；压缩级别无实测机制 |
| T0-3 健康/容量输出 | `24b7f29` | ✅ | ⚠️ | build/check 达成；**preview 读不到排队年龄与活跃数**（#15）；直方图 60 秒 reset 掩盖阻塞 |
| T1-1 角色配置 | `e80cf56` `f38a5a4` | ✅ | ✅ | 角色门禁是**真注销**（`vite.config.ts:124-163`），启动期校验齐备；仅 #11 拓扑仍单副本 |
| T1-2 独立预算 | `f38a5a4` | ⚠️ | ❌ | build/check/light 三 lane 确实独立；**preview 角色没有调度器**，相关变量全是死配置（#14）。plan:151 硬门槛未过 |
| T1-3 轻量通道 | `f38a5a4` | ✅ | ⚠️ | Runtime 侧 lane 分离正确；但超时只释放槽位不取消工作，且 CPU 密集期 `setTimeout` 不可触发；Backend 侧仍与诊断共用准入计数器（**M12**） |
| T1-4 分角色 Compose | `e80cf56` | ✅ | ⚠️ | 每角色都有显式 CPU/内存上限（门槛达成）；但 **#11** 副本数 = 1、**M6** 密钥过度注入、`compose.md:112` 指引已过期且照做会路由错 |
| T2-1 检查复用 | `b410d94` | ✅ | ⚠️ | 有界缓存 + in-flight 合并 + 鉴权逐次执行都对；**M2** 瞬态失败被长期缓存、**M11** 指纹三处缺口（资源/组件主题/编译器版本）；命中率指标无出口 |
| T2-2 构建持久领取 | `e156630` | ✅ | ❌ | 领取是**真 CAS**；但 **C1** 启动抢占、**C2** 围栏空窗、**M7** 提升非 CAS、**M9** 无续期、**M10** succeeded 无产物。「杀死执行实例/超时/迟到上传时最终结果只提升一次」的门槛**未达成** |
| T2-3 容量路由 | `fd09322` | ✅ | ⚠️ | 选址、冷却、`RUNTIME_BASE_URL` 回退与启动校验都对；**M3** 配置错误伪装成满载、**M4** 非幂等重发、**M12** 角色粒度过粗 |
| T3-1 预览授权可恢复 | `f38a5a4` | ⚠️ | ❌ | 换票链路建起来了、服务令牌可证明不下发浏览器；但 **C3** 缓存票据回退未修（且被本提交扩大）、**M1** 信任未验签的请求头、**M13** 通配令牌、票据校验欠规格。「任一副本仅凭当前请求与受信 Backend 完成鉴权」未达成 |
| T3-2 缓存有界化 | `9c0d58d` | ✅ | ✅ | `PreviewBoundedCache` 是真 LRU + TTL + 按 artifact 失效；内容身份与授权身份确实分离。仅「按条数不按字节设界」一处保留 |
| T3-3 摘流与版本指纹 | `eb75f20` | ⚠️ | ❌ | 被动摘流、Upgrade 透传、可更新 upstream 都对；但**版本指纹只报告不强制**（#17），排空无上界，且 `gateway-upstream.test.ts` 是配置文本正则而非真实网关回归（#11、#12） |
| T4-1 签名与共享 | `979d039` | ✅ | ✅ | **优秀**：fail-closed、kid 冲突守卫、JWKS 轮换、占位密钥拒绝、9 个测试对准门槛、轮换文档含 TTL 上限 |
| T4-2 Renderer attempt | `0896cc7` | ⚠️ | ❌ | 查询谓词正确（跨 epoch），但 `can_safely_remove_worker` **只有测试调用者 = 死代码**（#18），摘除前核对无任何可执行保证 |
| T4-3 多副本协调与 Run 停机 | `0f89c97` | ⚠️ | ❌ | 文档 + 测试为主；**M8** 代码是全局收敛而文档写「本进程」，两者相反；**#12** 测试证不了「多实例不重复提交产物」 |

**统计**：16 项任务中，代码全部落地 11 项、部分落地 5 项；plan 门槛达成 **5 项**（T1-1、T3-2、T4-1，及 T1-4 的资源约束部分）、未达成 **6 项**、部分达成 5 项。

---

## 8. 维护说明

1. 本文只记录 `e2efe6c..HEAD` 的落地评审；后续修复请在 plan「实施记录」或新评估中承接，不在本文上大改。
2. Critical/Major 的 `file:line` 以评审当时的 HEAD（`0896cc7`）为准；若行号漂移，以符号名定位：`recover_expired_build_jobs`、`recover_interrupted_build_jobs_on_startup`、`assert_attempt_fence`、`persist_uploaded_artifact`、`complete_job`、`recover_interrupted_agent_runs_on_startup`、`resolveTokenWithExpiry`、`readPreviewTokenCache`、`is_transient_check_result`、`is_transient_infrastructure_error`、`_build_theme_style_hash`、`_resolve_module_graph_identity`、`admission`、`can_safely_remove_worker`、`buildRuntimeServePlugins`、`isRuntimeBuildWorkerOomFailure`、`sendHtml`。
3. 修复某一项后，在 plan 实施记录中勾选并回链本文章节号（C1–C3 / M1–M13 / #11–#20），保持 README 状态一致。
4. **编号约定**：`C*` = Critical，`M*` = Major，`#11–#20` = §4「声称 vs 实际」表行号，未编号条目在 §4.2（Minor）与 §4.3（顺序/架构）。跨文档引用请带编号。
5. **复核口径**：本文所有 Critical 与 Major 均已对照源码逐行复核（非工具转述）；门禁结论来自实跑 `test:backend`（1021 passed / 9 skipped）、`test:runtime:gate`、`test:repository`、`test:contracts`。Minor 条目同样核过 `file:line`，但影响面判断含推断成分，修复前建议再确认一次。
