<!-- 文件功能：面向部署人员说明多 Backend 副本的共享存储与密钥前提、签名密钥轮换、旧票据语义、AI Run 停机语义与协调器幂等边界。 -->
# 多 Backend 副本与密钥一致性

多 Backend HTTP 副本是横向扩容的最后一步前置条件之一：任一副本必须能校验其它副本签发的票据、读取同一份产物，并用同一把密钥解密 AI 与 Renderer 凭证。SQLite Lite（`memory://lite` 与本地磁盘）**不支持**多 Backend；分布式部署请参考规划文档「Backend、存储与发布一致性前提」。

## 启动前提

在 `deploy/.env` 设置 `BACKEND_MULTI_INSTANCE=true` 后，Backend 启动时强制校验以下共享前提，任一不满足直接拒绝启动：

| 前提 | 要求 | 配置 |
| :--- | :--- | :--- |
| 签名私钥 | 所有副本读取同一把 RS256 私钥；禁止缺省自动生成 | `RUNTIME_RSA_PRIVATE_KEY` 或 `RUNTIME_RSA_PRIVATE_KEY_FILE`（共享路径 / Docker secret 挂载） |
| AI 凭证加密密钥 | 实例间同一把合法 Fernet 密钥，禁止默认/占位值 | `AI_SECRET_ENCRYPTION_KEY` |
| Renderer 服务凭证 | 实例间同一强随机密钥，禁止占位符 | `RENDER_SERVICE_CREDENTIAL_FILE` 或 `RENDER_SERVICE_CREDENTIAL` |
| 对象存储 | 所有副本可见同一产物存储 | `ASSET_STORAGE_DRIVER=s3`（推荐）；或共享卷 + `OBJECT_STORAGE_SHARED_VOLUME=true` |
| 运行态 | 真实 Redis（多副本共享） | `REDIS_URL=redis://…` / `rediss://…`，禁止 `memory://` |

`WEB_CONCURRENCY` / `UVICORN_WORKERS` 大于 1 时同样按多副本约束执行上述校验，无需显式声明。

单实例部署保持 `BACKEND_MULTI_INSTANCE=false`：签名私钥缺失时仍可自动生成 `data/runtime_rsa_key.pem`（仅限单实例/Lite），不影响现有开发与轻量部署体验。

## 签名私钥来源

`TokenService` 的 RS256 私钥按以下顺序解析（详见 `backend/app/services/signing_identity.py`）：

1. `RUNTIME_RSA_PRIVATE_KEY`：PEM 私钥文本（适合 secret 注入，不建议长期写在 env 文件）。
2. `RUNTIME_RSA_PRIVATE_KEY_FILE`：PEM 私钥文件路径——共享路径或 Docker/Kubernetes secret 挂载，**多副本推荐**。
3. 旧版 `data/runtime_rsa_key.pem`：兼容已有单实例部署。
4. 自动生成：仅当 `RUNTIME_RSA_ALLOW_AUTO_GENERATE=true` 且非多副本模式；写入 `data/runtime_rsa_key.pem`。

生成一把新私钥：

```powershell
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out deploy/secrets/runtime_rsa_private_key
```

JWKS（`/.well-known/jwks.json`）由当前密钥与轮换期旧钥共同构成，Runtime 通过 `RUNTIME_PREVIEW_JWKS_URL` 读取并校验预览/构建/诊断/服务令牌。

## 密钥轮换与旧票据语义

**策略：旧票据在自身 TTL 内仍有效，直到旧钥移出验签环。** 具体行为：

- 新票据一律用当前私钥签发，JWT 头携带 `kid=RUNTIME_RSA_KEY_ID`。
- 轮换期把旧钥放入 `RUNTIME_RSA_PREVIOUS_KEYS`（JSON 数组，每项 `{"kid": "...", "private_key_file": "..."}` 或内联 `private_key`）；旧钥仅用于验签与 JWKS 公布，不再签发。
- 带旧 `kid` 的票据只要未过 `exp` 就继续通过校验；过期票据一律按 `exp` 拒绝。
- 从 `RUNTIME_RSA_PREVIOUS_KEYS` 移除旧钥（或不带旧钥重启）后，旧钥签发的票据**立即失效**，这是明确的强制失效手段。
- 旧钥 `kid` 不得与当前 `RUNTIME_RSA_KEY_ID` 冲突，否则启动失败。

轮换步骤：

1. 生成新私钥，分配新 `kid`（如 `default-key-2`），写入 secret 挂载。
2. 滚动更新所有 Backend：`RUNTIME_RSA_PRIVATE_KEY_FILE` 指向新钥、`RUNTIME_RSA_KEY_ID=default-key-2`，并把旧钥写入 `RUNTIME_RSA_PREVIOUS_KEYS=[{"kid":"default-key-1","private_key_file":"…旧钥路径"}]`。
3. 等待已签发票据全部过期。TTL 上限取当前业务签发窗口：预览上下文/服务令牌默认 3600 秒，构建/诊断命令令牌默认 900 秒；建议至少保留旧钥 **1 小时**（覆盖最长 TTL）后再清理。
4. 从 `RUNTIME_RSA_PREVIOUS_KEYS` 移除旧钥并再次滚动更新；此后旧票据立即失效。

紧急作废（泄漏等）：跳过第 3 步，直接移除旧钥并重启全部副本；未过期的旧票据立即失效，客户端/预览会按鉴权失败重新换票。

## 凭证一致性说明

| 密钥 | 跨实例要求 | 轮换影响 |
| :--- | :--- | :--- |
| Runtime RSA 私钥 | 必须同一把（或轮换期共用同一验签环） | 见上节；旧票据 TTL 内有效 |
| `AI_SECRET_ENCRYPTION_KEY` | 必须同一把 Fernet 密钥 | **不支持直接更换**：更换后已有用户模型凭证密文无法解密，需先解密再重新加密迁移 |
| `RENDER_SERVICE_CREDENTIAL(_FILE)` | Backend 与全部 Renderer、全部 Backend 副本一致 | 可直接替换，但需同时更新 Backend 与 Renderer，旧令牌（HMAC，TTL 3600 秒）在轮换后失效 |

## 对象存储

多 Backend 的对象、截图与构建归档必须落在所有副本可见的同一存储：

- 推荐 `ASSET_STORAGE_DRIVER=s3`，各副本使用同一 `S3_*` 配置。
- 如使用本地目录，必须是跨副本共享卷（NFS/共享盘），并显式 `OBJECT_STORAGE_SHARED_VOLUME=true` 启动放行；该路径由运维自行验证共享性。
- `memory://lite` 与各副本本地独立磁盘不能充当共享产物存储。

## 任务协调器与不重复提交

多 Backend 副本下不依赖「恰好只有一个 Backend 进程」保证正确性。需要跨副本互斥的后台协调器统一使用数据库租约或条件更新（CAS）作为执行闸门：

| 协调器 | 互斥机制 | 说明 |
| :--- | :--- | :--- |
| 项目构建领取 | `ProjectBuildJob.claim_job` 条件 UPDATE + attempt 围栏 | 双协调者竞争同一任务只成功一次；产物仅在 attempt 与有效租约匹配时提升 |
| 页面截图队列 | `durable_job_lease_service.claim_pending_jobs` 条件 UPDATE | 请求内等待路径与队列循环共用同一租约协议 |
| 资源比例回填 / 页面变更 / 图片生成 / 组件变更 | 同上持久化租约 | 过期租约由 `recover_expired_running_jobs` 收敛 |
| AI 外部任务续跑 | `AiAgentExternalBatch` 租约代次 CAS | 同一 Batch 只能被一个协调者认领 |
| 渲染 attempt | `RenderAttempt` 租约 + 未释放检查 | 迟到结果不得覆盖新 attempt |
| 运行态 artifact 清理 | 各副本独立 sweep，操作幂等 | 仅按 TTL 释放过期键，不产生业务写入 |

创建接口上的 FastAPI `BackgroundTasks`（如 `POST /projects/{id}/build-jobs`）只是低延迟触发提示，**不是正确性依赖**：队列循环与 BackgroundTasks 可能对同一任务重复调用执行入口，但领取 CAS 保证最多一个执行者派发任务或提交产物。多副本部署时不要把这些进程内触发当作跨实例队列。

## 普通 AI Run 停机语义

普通智能体 Run 使用 Backend 进程内后台管理器（`AgentBackgroundRunManager`）执行，**不承诺跨实例无中断续跑**，也不承诺 Backend 重启后自动恢复。这是明确的产品语义，不是待修缺陷：

| 场景 | 行为 |
| :--- | :--- |
| 关闭侧栏 / 切换路由 / 断开 SSE | 只取消订阅，不取消执行；重新进入会话按 `event_index` 回放 |
| 用户点击停止 | 请求取消当前 Run，终态为 `cancelled` |
| Backend 正常退出 / 滚动重启 | 取消仍在执行的进程内任务，写入 `AI_RUN_PROCESS_STOPPED` |
| Backend 异常退出 | 由 active-run 空闲超时收敛，或下次启动时 `recover_interrupted_agent_runs_on_startup` 终态化 |
| 多 Backend 副本扩容 | 各副本各自收敛本进程 Run；**不得据此宣称普通 Run 可跨实例迁移或无中断续跑** |

停机后的用户可理解恢复路径：

1. **重试**：在原会话中基于已保留的消息、事件和工具调用记录重新发起同一目标；先确认上一轮是否已写入数据，避免重复执行。
2. **新建 Run**：直接在会话中提交新 Run；新 Run 继承会话消息历史与焦点快照，不继承中断 Run 的执行栈。

页面变更、图片生成等 external job 的领域执行走各自持久化租约队列，模型续跑统一由 `ai-external-task-coordinator` 认领 `AiAgentExternalBatch`，不与进程内 Run 管理器合并。若产品将来要求普通 Run 跨进程无中断续跑，必须另设可恢复执行与工具副作用幂等方案，不能仅替换锁提供者。
