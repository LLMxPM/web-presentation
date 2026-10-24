# 动画前版本联合验收记录

状态：本机联合联调、人工听感、Chromium 长稳和同版交付镜像组合已完成；N-1 旧镜像组合、真实 S3 和独立预览域仍待验收。候选分支 `feature/runtime-joint-acceptance-pre-motion` 从 `23d58aa` 创建；此提交是页内动画实现前的最后一个代码版本。本文只记录这条分支的验收范围与实际证据，不改变各专题的契约和阶段退出条件。

## 1. 候选范围

| 能力 | 本次验收范围 | 来源 |
| :--- | :--- | :--- |
| 私有文件、预览、截图与导出 | 受保护素材、真实 Renderer PNG、PDF/PPTX、构建产物与版本身份 | [文件鉴权规划](./file-storage-auth-cache-plan.md) |
| Three.js | 自包含 GLB 上传、预览、多实例、替换、真实截图、静态导出、构建与 CLI | [三维资源实施计划](./threejs-resource-implementation-plan.md) |
| 放映 | 单窗口及演讲者模式、`manual`/`timer`/`media_end`、全屏交互、静态捕获隔离与本地构建产物 | [放映验收计划](./slideshow/acceptance.md) |
| 音频 | M0 内容音频、M1 页面旁白、M2 项目 cue，覆盖资源、权限、媒体时序、双窗口与本地构建产物 | [音频验收计划](./audio/acceptance.md) |

本次不验收独立 MCP 仓的 model3d/audio 接入，也不验收远端无人值守及构建访问代理。CLI、主仓 External API、权限和能力协商仍在范围内。验收通过后只能按实际覆盖范围描述能力，不能宣称“完整外部 Agent 支持”或“远端无人值守”。页内动画、时间轴捕获与 `usePageTimeline.v1` 均不在本分支。

## 2. 音频联调开关

`23d58aa` 只正式开放 `audio_assets`。本分支增加 `AUDIO_DEV_CAPABILITIES_ENABLED`，默认 `false`；联合验收实例显式设为 `true` 时，旁白和 cue 的能力声明、写入门禁及 Runtime Kit 披露一起开放。验收结论不能自动改变正式开放集合 `AUDIO_OPEN_CAPABILITIES`。关闭开关后仍需核验既有旁白/cue 的读取、编辑、构建和错误语义，再决定是否逐阶段开放。

联合 E2E 还需在 Playwright 进程中显式设置 `PRE_MOTION_ACCEPTANCE_ENABLED=true`。只设置此变量、未开放 Backend 音频能力时，测试会在能力声明处失败；普通 E2E 不设置时跳过联合场景。两个开关各有明确职责，不能把 Playwright 标记当作服务端能力开关。

## 3. 联合场景与退出证据

1. 在独立测试工作空间上传 GLB、图片、MP3/M4A，建立含 3D 多实例、旁白、视频及 cue 的多页项目。记录资源 hash、页面版本、项目/路由原始放映配置和 Runtime 构建身份。
2. 验证 Editor 单页预览、全屏单窗口与演讲者双窗口：页面就绪和翻页动画结束后才开始旁白；`media_end` 等待参与媒体；前进/后退 cue 只触发一次；快速跳页、暂停/恢复、隐藏/重开窗口无旧声音或旧计时推进。
3. 在同一资源快照下生成真实远程 PNG、PDF、PPTX 和独立网页构建。检查 GLB 静态帧、音频静默、省略报告、画面尺寸/顺序与私有资源读取；捕获和导出不得启动自动放映。
4. 替换 GLB 和音频后，分别核对当前预览、历史 artifact、截图新旧身份与构建快照。验证错工作空间、过期票据、匿名访问和 Range/条件请求均按权限与版本拒绝或返回。
5. 通过 CLI 与主仓 External API 对模型文件、放映配置和音频配置做读改写回滚；旧客户端省略新增字段时不得清空。模板包导入导出保留资源与配置。
6. 对三维执行首帧/峰值内存测量、真实 PDF/PPTX 双视角目检和至少 50 次切换的资源增长检查；对音频执行原验收计划 A01–A20 的浏览器与长稳项目。记录实际浏览器、时长、次数、产物 hash、失败与未运行项。
7. 主分支合并前补真实 S3/独立预览域、同版部署和 N-1 镜像组合验证，并跑完整质量门禁。可跳过的只有本文明确排除的 MCP 接入与远端无人值守，不得以单元测试代替真实浏览器和部署证据。

运行浏览器联调时必须使用本分支服务和独立 `_e2e` 数据；不能把当前开发目录运行中的 `dev` 服务当作本候选版本。环境准备与测试选择遵循仓库 `dev-start-test` 技能；任何 E2E 重置前先确认服务归属。

## 4. 当前证据

| 项目 | 状态 | 结果 |
| :--- | :--- | :--- |
| 分支基线 | 已确认 | `23d58aa`；不包含 motion 代码 |
| 音频开关定向测试 | 已通过 | Backend 单元/API/契约共 19 项 |
| Backend 全量 | 已通过 | 最终连续门禁 1754 通过、22 跳过、0 失败；早期 Windows 20ms 模型流入口阈值波动已按测试调度余量修正 |
| Editor 门禁 | 已通过 | 898 项测试、类型检查与生产构建通过 |
| Runtime 门禁 | 已通过 | 最终 1226 项通过、3 项跳过；类型检查和生产构建通过。首次三端并行时 Mermaid 用例超时，单独复跑 7/7、Runtime 全套复跑通过 |
| 根仓契约与文档 | 已通过 | `test:contracts` 127 项、`test:repository` 63 项、生成契约无漂移。修复旧文档指向未入库临时报告的失效链接 |
| CLI Skill 与 Gateway 契约 | 已通过 | 工作树通过 `WEB_PRESENTATION_CLI_ROOT` 定位独立 CLI 仓，Skill 示例 4/4；真实 Nginx Gateway 契约通过。CLI 独立仓不含固定读取另一份主仓的跨仓测试时 203 项通过；CLI 0.3.5 在隔离 `_e2e` 库实际上传、下载、替换 GLB/WAV，读改放映和音频配置、创建两页及路由；替换过期 hash 返回 `ASSET_VERSION_CONFLICT`。临时 PAT 已吊销 |
| Renderer 与契约 | 已通过 | Renderer 42 项、渲染契约 26 项；Renderer 有 Windows 进程清理警告，测试退出码为 0 |
| Python workspace | 已通过 | 全成员共装、包边界及部署探针 17/17 |
| 真实浏览器基础回归 | 已通过 | 本分支独立 `_e2e` 服务，最终 18 通过、1 个联合音频场景按开关跳过；含真实远程 PNG、三维模型像素、PPTX、构建与 AI 页面写入 |
| 3D + 旁白 + cue + 放映联合场景 | 已通过 | 显式开放音频后的联合 E2E 1/1；GLB 静态截图有真实模型像素，进入全屏后旁白实际播放，切页 cue 与旁白分别调用两个音频资源。共用 GLB 夹具调整后原截图用例复跑 2/2 |
| 人工听感、模型与音频长稳 | 本机通过 | 用户实听确认旁白、短 cue 与退出全屏静音；模型页 50 次往返修复 WebGL 上下文线性增长；独立构建产物 Chromium 30 分 55 秒完成 1000 次 interaction cue、1000 次前进 cue、2000 次导航，结束后无播放中的音频 |
| 同版交付镜像组合 | 本机通过 | 候选 Lite、Runtime、Renderer 镜像真实启动；两个预览副本正常分发，跨发布身份的模块/CSS/Vite 请求各返回 409；真实 PNG、ZIP、离线站点和双 Build/Renderer 并发作业通过 |
| S3、N-1 镜像与生产预览域 | 待执行 | 按 §3 留存真实交付证据后再判定合并；本地回环预览不能替代真实 S3 和独立域 |

只有本分支门禁、联合场景和发布部署条件均有证据时，才建议合入 `main`。[发布检查表](../../deployment/release-checklist.md)中仍适用的基础设施事项需同步关闭或明确限制发布面。

### 2026-10-24 本机补充证据

- 本机隔离 `_e2e` 库、Redis DB 15 和候选分支服务中，真实 CLI 创建含双视角 GLB、内容音频、4 秒旁白、`interaction.confirm` 与 `transition.forward` 的两页项目。项目 3、页面 4/5 及资源 6/7/10 仅是本轮临时测试 ID；CLI 配置另放在忽略目录，未修改用户原有 profile。
- Renderer 的双视角 PNG、浏览器导出的 PDF/PPTX 均看见两个不同视角；PowerPoint 实际打开并导出 PNG 后也看见两个模型。静态 PDF/PPTX 过程中记录到 0 次媒体 `play()`。独立 ZIP 构建任务 2 成功，SHA-256 为 `8d3b1300d7b353042f9a90d4a4081074d50aa45080e4d048bca5d2378663b03a`，包含 GLB 与两份 WAV，可脱离 Backend 和外网加载。
- 相同 ZIP 的模型页与音频页往返 50 次，GC 后 DOM 节点始终 511、监听器始终 80、文档数始终 4；JS 堆约 8.21→8.57 MiB。原实现每轮留下两个已绘制 WebGL 上下文，已通过空闲渲染器池修复；同时显示的模型仍使用独立实例。浏览器对照实验确认简单 WebGL 与未绘制 Three.js 实例没有该增长，修复后重建 ZIP 复测通过。
- 资源版本从绿色 GLB `1c33068256254ef6c67904d834b204b7091f1151370c5b51caeb16e274bfe095` 替换为红色 `4148b466fb7d05e0f08eaeebed523843672ddd6e46a10c52d59ff4e58385faef`：旧 artifact 仍显示绿色，新 artifact 显示红色；Renderer PNG 绿色像素 104801→0、红色像素 399→106421，截图内容 hash 改变。旧构建 ZIP 保留绿色快照。
- 音频受保护读取在真实 HTTP 下返回 Range 206/200 字节、HEAD 200、ETag 304；匿名 401、错误 hash 404、错误工作空间 404、错用途票据 401。模板包导出 99554 字节，SHA-256 `1fdd50915eeb9c027e353e126f4585d4c610ad8bcd7277d7e4b61c99fac4086b`；导入新项目保留两页、3 个资源摘要、两条 cue 与放映配置。由此发现并修复导出预检把实际放映配置误显示为默认值的问题，新增单测。
- 独立 ZIP 的 Chromium 音频长稳报告在 `test-results/pre-motion-acceptance/audio-soak.json`：30 分 55 秒、1000 次 interaction cue、1000 次前进 cue、2000 次前后导航，2000 次 cue `play()`、0 次拒绝、0 个外部请求、0 个脚本错误。导航阶段 GC 后堆约 8.93–10.09 MiB、节点 736–760；后续 11 次长稳采样堆约 10.06 MiB、节点 736、监听器 93、媒体元素 2，退出全屏 3 秒后播放中元素为 0。用户实听确认旁白、cue、退出静音三步符合预期。
- 真实 Chromium 注入一次旁白 `NotAllowedError` 后出现受阻提示，点击重试恢复到“媒体播放中”；演讲者双窗口两次进入音频页，观众旁白播放计数 2、控制台 0，关闭观众后控制台仍为 0。关闭 `AUDIO_DEV_CAPABILITIES_ENABLED` 后，能力声明关闭，已存两条 cue 和旁白页可读，元数据更新不清空 cue，非空 cue 写入返回 422，清空成功，历史项目预览与构建任务 4 成功。
- 专属 Docker 项目 `wp-arch-drill-a90b2f62` 使用候选 Lite `sha256:4d5e3e32`、Runtime `sha256:e81fe987`、Renderer `sha256:929ba5b2`；同版浏览器跨两个预览副本记录 64 条脱敏响应。发布身份冲突时，`main.ts`、Tailwind CSS 与 Vite 客户端各返回 409 `PREVIEW_VERSION_SKEW`。6 个凭证负例均拒绝启动；官方部署探针下载 1920×1080 PNG（SHA-256 `1739246ffbe5196059043504f2dba55fde8230f106128ac9b0f4589eedcbf633`）与 ZIP（SHA-256 `780c426a02b4d9466f5fb5f290ba9a9fd974e14e8200f53e227ebbea8ca2784d`），ZIP 经本地 HTTP 在 Chromium 实际打开。4 组独立作业由两个 Build Worker 和两个 Renderer 分担并下载产物。证据在 `test-results/docker-architecture/wp-arch-drill-a90b2f62/`。
- 演练过程中修复了三处测试探针问题：新预览副本需要在 Gateway 分流前等待就绪；本机 Playwright HTTP 客户端把 `preview.localhost` 解析到代理地址，409 正文复核改为保留原路径、查询和 Host 并连接本轮回环 Gateway；构建站点同时有主画布和缩略图，标题断言已限定到实际可见的主画布。这些修复未改变产品预览协议。
- 最终执行 `node .agents/skills/dev-start-test/scripts/full-test.mjs` 连续通过：Backend 1754/22 跳过、Editor 898、Runtime 1226/3 跳过、根仓契约 127、渲染契约 26、Renderer 42、Python workspace 17、完整 E2E 18/1 跳过。仓库文档门禁另有 63/63。此前一轮 Editor 路由测试发生一次 5 秒超时，定向 17/17 与后两轮完整 Editor 均通过；另一轮根仓收集边界仍期望 1 个 `runtime-heavy` 用例，已同步为默认收集 2 个、联合场景按开关跳过。Renderer 单独补测曾在 Windows 槽位用例处卡住一次，终止本轮 pytest 后定向 24/24、整套 42/42 与最终连续门禁均通过。保留这些波动记录，不将失败轮次描述为通过。

上述长稳只覆盖 Windows Chromium 与本轮小型自制 GLB/WAV。MP3/M4A/OGG 的实机播放、复杂纹理/骨骼 GLB 的容器峰值、真实 S3/独立预览域和 N-1 组合尚未由本轮证据关闭；不能把本地小样本外推为全部格式或发布拓扑通过。
