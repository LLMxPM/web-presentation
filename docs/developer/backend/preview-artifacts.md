# 预览 artifact 与构建任务

Backend 负责把平台数据转换为 Runtime 可执行的短期上下文和构建快照。

## preview artifact

preview artifact 是 Runtime 预览页面或组件时读取的短期上下文。它应包含当前对象渲染所需的源码、配置、资源引用和访问令牌，不应长期保存。

临时预览 artifact 存放在**运行态存储适配器**中（`runtime:artifact:*`，默认 TTL 3600 秒，诊断链路结束主动删除），因此：

- 常规 Redis 部署缺少缓存时可从持久化快照重建；SQLite Lite 使用进程内 `memory://`，**重启或 TTL 到期后临时预览失效**。
- 失效表现为访问旧 `rt_` 地址 404 / `PREVIEW_ARTIFACT_UNAVAILABLE` 一类提示，用户动作是重新打开预览；平台不伪称自动恢复，也不会让旧 `rt_` ID 悄悄指向新内容。
- 数字 Release artifact 与构建产物走主库与产物托管，重启后仍可访问。
- 容量受 `RUNTIME_STATE_MEMORY_MAX_BYTES` 约束，超限写入在生效前拒绝，不留下半个 artifact。

契约与 key 归属见 [运行态存储适配器](./runtime-state-adapter.md)。

## 截图任务

截图由 Backend 持久化渲染请求并调度独立 Renderer；Renderer 在 Chromium 中加载 Runtime 预览页面，回传截图结果。需要关注 viewport、超时、并发和 visual-ready 等参数，避免截图队列阻塞。Backend 不直接启动浏览器。

页面创建与源码编辑可在 `page.diagnose` 的同一 attempt 中附带 PNG。诊断先完成，再进行静态视频帧和捕获画面准备；图片阶段最多使用剩余硬期限内的 10 秒。编译/布局诊断失败仍拒写，诊断完成后的图片失败只让截图处于 `pending`，不重开浏览器。

新建任务持久化 `candidate_code`，正式保存必须使用同一编码；冲突重新规划。单页 artifact 的 `entry_page` 只下发已知的 code、title、speaker_notes，候选不伪造尚未分配的页面 ID。Runtime 以该元数据构建单页宿主标题与备注。新增路由等无法与候选一致的上下文变化会使附图失效，后续截图需求走原队列。

临时 PNG 独立于输入 artifact，引用携带 workspace/request/attempt/hash/大小/有效期。公共 `validation_screenshot_publisher` 在事务外复制并登记 10 分钟持有，事务内复核最终源码闭包、实时资源、主题字体、路由元数据、画布、Runtime 构建与捕获策略后，和页面及 Job 结果一起发布。`page_screenshot_artifacts` 维护页面范围内的历史内容映射；取消、事务失败和崩溃遗留由原渲染协调器每分钟执行过期回收。输入 artifact 清理不会删除输出图。

## build snapshot

build snapshot 是一次项目构建的固化输入。构建开始后 Runtime 应基于 snapshot 执行，不应继续读取可能变化的项目状态。

## 构建任务

构建任务记录状态、日志摘要、产物位置和错误信息。失败时应尽量保留可诊断信息，方便区分源码错误、资源缺失、Runtime 不可用和上传失败。

任务状态、产物元数据与 Release 是**主库事实源**；`runtime:build:*` 运行态缓存只用于进度与心跳，缓存写入失败不阻断任务创建，也不改变状态查询结果。进程在构建中重启时，遗留 `running` 任务由启动恢复收敛为可解释的失败，已成功的构建产物仍可下载，重新触发即可得到新任务。运行态被清空不影响任务领取、租约与终态判定。

## 产物托管

Runtime 构建完成后把 zip 或静态产物上传回 Backend。Backend 负责保存产物并提供稳定下载或静态访问地址。
