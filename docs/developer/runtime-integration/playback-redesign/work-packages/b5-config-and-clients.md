# B5 配置与调用端收敛

状态：待实施。主责：Backend / Editor / AI / CLI。前置：[B2](./b2-completion-aggregation.md)。出口：GB。

## 交付

- Backend 放映配置直接重定义为 `manual/timer/scene_end`、定时值、完成后停留、末页循环、翻页过渡与音频 cue；删除 `auto_start`（`schemas/slideshow.py:116`、`core/slideshow_defaults.py:13`、`models/workspace.py:96`）、`media_end`、`timeline_end` 与对应超时字段。提升 schema 版本，并定义旧预览 artifact 与已生成构建快照读到旧版本时的失败语义；不复用旧版本号承载新字段含义。
- 放映默认值的真实落点是 `backend/app/core/slideshow_defaults.py` 与 `backend/app/schemas/slideshow.py`；`backend/app/config_templates/` 的 yaml 目前不含放映字段，Runtime 侧另有 `runtime/public/config/*.config.yaml`。改动前先确认落点，不要假设模板包已有这些字段。
- **Editor 配置表单与 DTO 同批落地**：只展示新推进模式、停留时间、完成后停留、过渡与 cue，移除旧字段；预览与放映入口保留播放、退出及演讲者自动翻页 `hold/release`，删除页内进度、定位、Scene 暂停与重播控件；不再提供会话级自动/手动配置切换入口。UI 遵守 `DESIGN.md`，数据层使用生成类型，不增加手写镜像 DTO。
- **Presenter 协议收敛为最小意图与原子状态**。现状 v4（`runtime-shell/presenter/presenter-sync-protocol.ts`，528 行；控制器 `usePresenterController.ts`，852 行）的 7 类消息、8 种播放状态、8 种命令动作与 9 种时间轴阶段，收敛为演讲者窗口发 `start/next/stop/hold/release` 等有限用户意图，观众窗口作为唯一调度者回传 `{page, phase, revision, ownerId}` 与必要的受阻/失败摘要。删除时间轴位置、剩余时长、复杂 ack/重放与双调度逻辑；同一 owner 的旧 revision 必须拒绝，重开时明确获取当前状态，不能把绝对状态当作天然乱序安全。旧 v4 快照不兼容、不做降级协商。
- 观众窗口交互面写清：本地点击播放与静音可重试受阻媒体；全屏请求不保证后续自动播放获准。观众窗口负责 Scene 与媒体完成事实，演讲者窗口沿用 `interactive-preview` 策略，不自动播放媒体；演讲者的点击不能替代观众窗口的播放许可。
- 清理 `core/execution/execution-policy.ts` 的 `allowPresenterSync` 死标志：除 `mergeExecutionPolicies` 的与运算外全仓无消费者（其余四个 `allow*` 都有对应判定函数）。要么给它真实语义（在宿主初始化前拒绝同步参数），要么删除；缩略图与捕获链路的隔离本来就由 thumbnail 档禁媒体禁推进和 `resolveExecutionContext` 忽略 `channel` 参数保证，不依赖该标志。
- `PresenterPageGrid.vue` 每页渲染一棵真实 Vue 组件树（`ViewPreview` + `inert`），成本随页数线性增长。本包只记录实测页数上限与卡顿边界，不重构；该成本与双窗口同步无关，缩略图不参与同步链路。
- AI 以 `backend/app/ai/tool_specs.py` 为单一事实源更新，并同步派生文件：`backend/app/ai/animation_authoring_standard.py`（当前有多处 `usePageTimeline` 与 `Asset*.v2` 指引）、`ai/tools/generic/business_tools.py`、`agent_catalog.py`、`tools/disclosure.py` 与防漂移测试。去掉任意时刻截图与旧推进模式建议，新增 Scene 写法、真实片段索引与签名、自动发声主媒体限制、B0 静态态声明、`STATIC_PRESENTATION_UNAVAILABLE` 与资源/基础设施失败的区别；明确不支持 GSAP 插件、粒子只能用 DOM/CSS/Canvas。
- 提供一个真实端到端创作样例与有界负例（数字滚动、打字机、SVG 描边、DOM/CSS/Canvas 粒子、两个模型动作、旁白与 cue），取代 G2-05 的量化门槛；CodeCheck 与页面 Mutation Job 走现有受信 Renderer 验证链。
- 跨仓 CLI：读写新放映配置；截图结果区分 `ready`、`pending`、内容 `unavailable`、任务 `skipped` 与执行失败，展示稳定原因码；删除旧时间轴与旧推进模式的命令与示例，同步 Skill 与包版本。已知涉及 `packages/cli/src/wp/commands/` 下的 `project_slideshow.py`、`screenshot.py`、`project_audio.py`、`page.py`、`project_route_add.py` 与 `skills/web-presentation/references/motion-authoring.md`。
- External API 变化会使 `web-presentation-mcp` 的契约快照与 bindings 失配：同步刷新其快照，或明确记录该失败为非阻塞。

## 验收

API、服务与契约测试覆盖项目继承、逐路由覆盖、权限、快照往返、非法枚举、未知字段、cue 资源引用；双窗口协议测试覆盖有限意图、观众窗口唯一调度、原子状态重复与旧 revision 拒绝、观众窗口重开对齐、受阻摘要、`hold/release` 不连跳及演讲者窗口不自动播媒体；Editor 类型检查、单测与构建通过；工具规格/披露防漂移与 AI 页面任务测试通过；独立构建使用快照中的新配置。数据库结构变更验证 SQLite 与 PostgreSQL 适配边界。CLI 在其仓库提交与验证，主仓只做 External API 对拍。
