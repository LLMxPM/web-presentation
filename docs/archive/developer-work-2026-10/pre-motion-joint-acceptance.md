# 动画前版本联合验收记录

> 本文记录 2026-10-24 至 25 的候选分支及当时默认关闭旁白、cue 的验收状态。2026-10-25 后续改动已将两项能力默认开放；当前状态见[音频计划](audio/plan.md)。文中的候选结论和开关描述保留为历史证据。

状态：本机联合联调、人工听感、Chromium 长稳、同版交付镜像、上一正式发布版 `v0.3.1` 升级组合及三个高风险合并样本已完成，可以进入 `main` 合并评审；真实 S3 和独立预览域仍待发布验收。候选分支 `feature/runtime-joint-acceptance-pre-motion` 从 `23d58aa` 创建；此提交是页内动画实现前的最后一个代码版本。本文只记录这条分支的验收范围与实际证据，不改变各专题的契约和阶段退出条件。

## 1. 候选范围

| 能力 | 本次验收范围 | 来源 |
| :--- | :--- | :--- |
| 私有文件、预览、截图与导出 | 受保护素材、真实 Renderer PNG、PDF/PPTX、构建产物与版本身份 | [文件鉴权规划](../../developer/projects/file-storage-auth-cache-plan.md) |
| Three.js | 自包含 GLB 上传、预览、多实例、替换、真实截图、静态导出、构建与 CLI | [三维资源实施计划](../../developer/projects/threejs-resource-implementation-plan.md) |
| 放映 | 单窗口及演讲者模式、`manual`/`timer`/`media_end`、全屏交互、静态捕获隔离与本地构建产物 | [放映验收计划](slideshow/acceptance.md) |
| 音频 | M0 内容音频、M1 页面旁白、M2 项目 cue，覆盖资源、权限、媒体时序、双窗口与本地构建产物 | [音频验收计划](../../developer/projects/audio/acceptance.md) |

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
7. 主分支合并前完成本机同版部署、上一正式发布版升级组合、真实浏览器核心用户路径和完整质量门禁；对外发布前另补真实 S3 与独立预览域。MCP 接入与远端无人值守不在本候选验收范围。代码合并与发布分别按 §5 的停止条件判定，不以单元测试代替真实浏览器和部署证据。

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
| 上一正式发布版 `v0.3.1` → 候选 | 本机通过 | 整套旧平台/Lite/Runtime/Renderer 镜像按 digest 拉取；两套独立 PG 项目验证旧版预览、PNG、ZIP、浏览器加载，原库升级后候选复验及旧 ZIP 回读；混版行为见 §5 |
| 合并前高风险样本 | 本机通过 | 带纹理与骨骼 GLB 在预览、远程 PNG、PPTX 真实出图；50 次切页后原生 canvas 2→2；MP3 手动播放、离页停播、静态 PPTX 禁播通过；三页真实全屏与演讲者键位 17 项通过，见 §6 |
| S3 与生产预览域 | 待发布验收 | 本地回环预览不能替代真实 S3 和独立域；不把本机组合验证写成生产发布通过 |

只有本分支门禁、联合场景和 §5 的合并停止条件都有证据时，才建议合入 `main`。对外发布还须关闭或明确限制[发布检查表](../../deployment/release-checklist.md)中的基础设施事项。

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

上述 2026-10-24 长稳只覆盖 Windows Chromium 与小型自制 GLB/WAV。§6 另补一个 MP3 与一个纹理骨骼 GLB；M4A/OGG、复杂模型的更大容器压力样本、真实 S3/独立预览域仍未关闭，不能把本地样本外推为全部格式或发布拓扑通过。

## 5. 上一正式发布版与合并边界（2026-10-24）

本候选的上一正式发布版是 `v0.3.1`（Git 提交 `a94ae5703c99237eb9b9c5799722c7f54310f4d2`，2026-10-15）；候选基线 `23d58aa` 为其后代。历史 M05 的 `4c7eee8` 是另一轮固定兼容样本，不代表本轮上一正式发布版。Docker Hub 公共标签元数据与阿里云 ACR manifest 对应四个相同 digest；本机 Docker Hub Registry HEAD 经代理返回 EOF，实际从 ACR 按 digest 拉取。四镜像 OCI revision 均为 `a94ae57`：

| `v0.3.1` 镜像 | digest |
| :--- | :--- |
| platform | `sha256:5e9b439365ce263d48afacd4ca3163d7e49fa428d112e1ed4660b8c941f6b176` |
| Lite | `sha256:07b7d16b0d03eb3985aad196b16ed138c8773576b7308e8cc33db3944c250bb9` |
| Runtime | `sha256:93fb12ffece9fa8831c396cdbf177b4d4296474c4f5d72b7ac31fb9a7e64b53b` |
| Renderer | `sha256:bb3d85ad0d2ac2b8274d62bc402bc98f2441f4d2cb69b72cdfb39109ab1467ef` |

两个独立项目分别以旧 platform 或旧 Lite 作为 Backend，均使用整套旧 Runtime/Renderer、独立 PostgreSQL/Redis/卷和回环 Gateway；旧版同版浏览器 57 条响应、真实 1920×1080 PNG、ZIP 与浏览器加载均通过。停旧后由候选 platform `sha256:66ae1f35` 将原库从 `20261002_0100` 迁到 `20261019_0100`，再以候选 Runtime `sha256:e81fe987`、Renderer `sha256:929ba5b2` 启动。两套项目的候选浏览器 64 条响应、PNG、ZIP 与旧 ZIP 经新 Backend 下载并重新加载均通过；旧 ZIP 摘要保持不变。演练 Backend 使用 `uvicorn` 入口，未覆盖交付镜像的默认 CMD 或 SQLite 前滚。证据位于 `test-results/docker-architecture/wp-arch-drill-4c4d7f6d/` 与 `test-results/docker-architecture/wp-arch-drill-2735d2eb/`，项目容器和卷均已清理。

混版探针只给出本轮具体组合的结论：候选 HTML 的版本化模块/CSS/Vite 请求落到旧 Runtime 副本时均以 409 `PREVIEW_VERSION_SKEW` 拒绝；候选 Backend + 整池旧 Runtime 的 `/runtime/__preview` 为 401，页面不渲染；候选 Backend/Runtime + 旧 Renderer 的真实 PNG/ZIP 成功。发布仍采用排空旧 Runtime 池、同版切换，不能把单个 Renderer 兼容样本外推到任意旧版。第二套项目并行时 Docker Desktop API 短暂 500、就绪探针超时，释放第一套项目资源后候选浏览器 64 条响应在约 10 秒内通过；失败轮次与续验报告均保留，不将首次超时记成通过。

**代码合并停止条件（2026-10-25 本机已满足）**：保持正式音频能力 `audio_assets` 开放、旁白与 cue 默认关闭；联合用户路径、用户实听、真实截图/导出、长稳与完整质量门禁已有证据。三个高风险样本的补证见 §6，均未发现阻断问题；本分支可进入 `main` 合并评审，合并仍以审阅、CI 和无新回归为准。

**发布停止条件**：真实 S3、独立预览主机名的 Cookie/CORS/票据与受保护素材链路、正式部署版本与回滚窗口必须实测。M4A/OGG、复杂 GLB 的更大压力样本、Firefox/WebKit 按实际支持范围继续补证；未经实测不得宣称全格式或跨浏览器支持。MCP 和远端无人值守依旧不纳入本候选发布面。

## 6. 合并前高风险样本补证（2026-10-25）

沿用当前候选的隔离 `_e2e` 四服务，在独立三页项目中上传 [Khronos Cesium Man GLB](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/CesiumMan/glTF-Binary/CesiumMan.glb)（438044 字节，SHA-256 `b7001eaeea8254bd44773bcd247e78696d94169388fbb2a1800fc69434e777d9`，含 1 个纹理、1 个 skin、1 个动画）与 [MDN 示例 MP3](https://developer.mozilla.org/shared-assets/audio/t-rex-roar.mp3)（39868 字节，SHA-256 `41191d0727073bf848bcc8f0bd851d71a0b0058e901abb1c1b236ad327bda52e`）。样本只存于忽略目录与 `_e2e` 数据，不进入仓库或发布包。

- 模型：真实预览、独立 Renderer PNG 和可编辑 PPTX 内的模型图像均经像素目检，无空白；PNG 1920×1080，PPTX 为 1 页且含模型 PNG。主画布与音频页往返 50 次后模型仍可见，Chromium GC 后原生 canvas 2→2、节点数在后五个采样点均为 459、监听器均为 105，未见 WebGL 上下文过量警告或脚本错误。报告与图片为 `test-results/pre-motion-acceptance/high-risk-model.json`、`high-risk-model-switch.json` 和相邻 PNG/PPTX。
- MP3：主画布原生 audio 解码时长 2.074 秒，默认暂停；点击页面按钮后 `currentTime` 推进且未结束，离页动画结束后旧元素暂停并卸载、页面播放中元素为 0。静态 PPTX 导出前后浏览器 `play()` 调用数均为 1，产物 1 页且未嵌入音频文件。报告为 `test-results/pre-motion-acceptance/high-risk-mp3.json`；缩略图音频的 `preload=none`、媒体策略 `block` 是预期静态隔离，测试只以主画布 `allow` 音频判断手动播放。
- 键位：在上述三页项目的真实 Chromium 全屏中，`→`、`←`、空格、Home/End、PageUp/PageDown、上下方向键与数字键均命中预期单页，首个 `→` 停在中间页而非跨两页。演讲者控制台左右键同步观众，观众窗口键盘只读，控制台空格不翻页，共 17 项。报告为 `test-results/pre-motion-acceptance/high-risk-keyboard.json`。

这些补证只覆盖 Windows Chromium、本轮两个具体素材与隔离回环部署；更大模型、其它音频格式及真实发布拓扑仍按上方发布停止条件判定。最初 MP3 探针误选缩略图中的禁播 audio、最初离页断言早于 200ms 过渡完成，均已修正测试定位与等待条件后重跑通过；未修改产品代码。

## 7. 发布环境的三项待验收门槛

以下测试使用隔离测试库、私有测试桶和测试域名，固定候选平台 / Runtime / Renderer 镜像 digest；不复用生产数据。先完成前两项，再做升级与回滚演练。结果记录配置项名称、镜像 digest、DB revision、响应状态和耗时，日志不得保存完整票据或 S3 密钥。它们不替代[发布检查表](../../deployment/release-checklist.md)中的其它事项。

1. **真实 S3 兼容服务**：以 `ASSET_STORAGE_DRIVER=s3` 连接目标提供商的私有测试桶，配置 `S3_ENDPOINT_URL`、凭证、bucket 和 region；本地内存替身或本机 MinIO 只算预演。上传图片、字体、GLB、MP3 和构建产物，分别在冷缓存、热缓存及两个 Backend 副本上验证同一字节与版本；走浏览器单页 / 整项目预览、Renderer PNG、PDF/PPTX 导出和构建 ZIP。对受保护文件实测 GET、HEAD、Range 206、ETag 304 / If-Range，以及匿名、错工作空间、过期票据、失效缓存的拒绝；桶匿名读取始终失败，旧字体桶若存在也须关闭公开 ACL。留存 S3 响应头、文件 hash、任务终态与回源量，判定标准见[文件鉴权验收矩阵](../../developer/projects/file-storage-auth-cache-plan.md#11-验证矩阵与性能证据)。
2. **独立预览域**：准备两个不同主机名及有效 DNS/TLS，例如业务域 `presentation.test.example` 与预览域 `preview.test.example`，可指向同一 Gateway；只换端口不算隔离。设置 `BACKEND_PUBLIC_BASE_URL`、`RUNTIME_PUBLIC_BASE_URL`、`RUNTIME_SERVER_BASE_PATH` 和只含业务域的 `CORS_ORIGINS`。真实浏览器检查用户页面运行在预览域 iframe，业务登录 Cookie 为 host-only 且不随预览请求发送；预览域发起业务写请求被拒绝，`/runtime/` 模块、字体与 `/build-artifacts/` 受保护子资源正常加载。匿名 / 过期票据不能取私有资源，版本不符明确返回 409；截图与导出仍成功。配置与转发见[生产域名说明](../../deployment/production/README.md#公网-url-配置)。
3. **回滚窗口**：升级前约定可撤回时段及 RPO/RTO，保留 `v0.3.1` 和候选的精确镜像、数据库与 S3 对象一致备份、密钥和配置，并记录旧 `alembic_version`。在同拓扑隔离环境按「排空任务和旧池 → 停旧 Backend → 备份 → 候选迁移 → 同版新池验证」演练，再故意执行一次回退。先验证旧应用能否在候选 schema 上工作；只有通过完整读写、登录、预览、PNG 与 ZIP 后才允许保留新库做应用回滚，否则须停写并恢复与旧镜像匹配的数据库和对象备份。记录实际中断时长、数据恢复点、旧产物 hash 和失败轮次；不得通过 `alembic stamp`、重开 `/media` 或公开桶使旧版表面可用。当前 `v0.3.1` → 候选只完成前滚，**没有**旧应用在新 schema 上的回滚证据，详见[升级与回滚](../../deployment/operations/upgrade-rollback.md)和[备份恢复](../../deployment/operations/backup-restore.md)。
