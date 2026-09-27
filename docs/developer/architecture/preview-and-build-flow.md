# 预览与构建链路

预览、截图与构建由 Backend 协调。Editor 发起用户操作，Runtime 提供页面渲染和构建能力；真实 Chromium 截图与页面诊断由独立 Renderer 执行。

## 页面预览

1. Editor 保存页面源码或配置。
2. Backend 校验用户权限和源码导入边界。
3. Backend 创建 preview artifact，并为 Runtime 签发短期上下文令牌。
4. Editor iframe 访问 Runtime 预览入口。
5. Runtime 回源 Backend 读取上下文、配置包、资源和远程模块。
6. Runtime 渲染页面并把结果展示给 Editor。

页面 iframe 使用版本 1 状态消息回传最终结果：成功发送 `page-preview:ready`，初始化或页面模块失败发送 `page-preview:error`；payload 必须包含当前 `artifactId`。Editor 同时校验消息窗口、origin、协议版本和 artifact，忽略旧预览迟到消息。Editor 在等待 8 秒后展示弱网提示，30 秒后进入可重试错误；超时不会销毁 iframe，因此同一 artifact 的迟到 ready 仍可恢复预览。

## 组件预览

组件预览依赖组件源码和 previewSchema。Backend 负责校验 previewSchema 可导入能力，Runtime 负责按 schema 渲染典型状态。previewSchema 变化时要同步 Runtime 组件预览测试和 Backend 契约测试。

组件预览沿用 `component-preview:ready/error` 消息，在 Editor 中采用与页面预览一致的 8 秒弱网提示和 30 秒可重试超时。刷新同一预览对象时保留旧 iframe 并覆盖加载状态；切换对象时清空旧画面，避免串用 artifact。

## 截图

1. Backend 持久化渲染请求，并按租约和并发限制调度受信 Renderer。
2. Renderer 为本次执行创建独立 Chromium 和 Context，加载 Runtime 的受保护预览页面。
3. Renderer 等待页面就绪，生成截图或诊断结果并回传 Backend；Backend 关联任务与产物。

截图任务需要关注 viewport、超时、并发、资源加载和页面 visual-ready 状态。Backend 进程不直接启动浏览器。

## 项目构建

1. 用户在 Editor 发起项目构建。
2. Backend 创建 `ProjectBuildJob` 持久任务（含 `attempt_id`、租约字段和创建时即确定的绝对 `deadline_at`）并生成 build snapshot。
3. `runtime-build` 内的 Build Worker 按 project lane 并发启动等量领取消费者，通过 `POST /internal/runtime/build-jobs/claim` 以条件更新认领任务；Backend 下发 attempt 令牌，并把租约与令牌 TTL 一并裁剪到 `deadline_at` 之前。
4. Worker 执行期间周期调用 `renew`：收到 401/409 立即中止在跑构建，与 Backend 失联时也在本地租约到期（留出安全余量）前主动停手，避免失守的执行者继续消耗资源或抢写状态。
5. Runtime 拉取 snapshot，生成临时入口并在隔离子进程内执行 Vite 构建与 ZIP 归档；构建子进程不继承 Worker 领取凭证。中止信号一路传到子进程本身：租约失守或 deadline 到期时先 `SIGTERM`，宽限 1 秒未退出再 `SIGKILL`，并等到真实 `close` 才释放调度槽位与临时工作区。只中止主进程的 `fetch`/`sleep` 会让最耗 CPU 与内存的构建阶段继续跑到自然结束。
6. Worker 以 `POST /internal/runtime/build-jobs/{job_id}/artifact` 上传产物：归档按分块流直接作为请求体，入口文件与 sha256、大小通过 `x-runtime-build-archive-*` 头声明，两侧都不再把整包读进内存，Backend 超过 `PROJECT_BUILD_ARTIFACT_MAX_BYTES` 即中止写入。校验和/大小不符、attempt 围栏失守或提交异常时，Backend 会删除这个没有任何行引用的 attempt 归档，避免对象存储积累 orphan；仍被任务行引用的产物一律保留。上传成功后调用 `complete`。Backend 只在 `attempt_id` 与**有效租约**同时匹配时才提升产物或写终态，失守的执行者只能留下等待恢复的 `running` 行。
7. `complete(success)` 对同一 `attempt_id` 幂等：任务已是 `succeeded` 且产物已提升时返回 200 而不是 409，Runtime 侧对传输失败与 5xx 再做最多 3 次重试。否则「产物已上传、complete 响应丢失」只能等租约过期，用户会看到产物已生成但任务仍 `running` 十几分钟。4xx 是确定性拒绝，不重试。
8. 恢复循环按过期租约接管或收敛：已经上传产物的任务收敛为 `succeeded`，超过总期限仍未被领取的任务收敛为 `failed`。

构建不存在第二跳执行路径：Backend 不再向 Runtime 同步派发构建，Runtime 也不暴露构建 HTTP 入口。凭证未配置时 Backend claim API fail-closed 且 Worker 不启动，构建任务停留在 `pending` 直到总期限把它收敛为失败。`RUNTIME_ROLE=build` 的容器在这种情况下直接启动失败，`/__runtime_readyz` 也不会就绪——「进程健康但永远不构建」比启动失败更难发现。

## 关键约束

- 页面源码、组件源码和 previewSchema 只能引用 Runtime Kit manifest 公开且版本化的能力。
- Runtime shell 内部能力不进入页面、组件或 AI 能力目录。
- 构建 snapshot 应固化当次构建所需上下文，避免构建过程中读取漂移状态。
- 预览 artifact 和构建心跳属于临时运行态，应有 TTL 和恢复策略。
