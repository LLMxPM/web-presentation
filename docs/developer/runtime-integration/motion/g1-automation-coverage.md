# G1 自动化与隔离浏览器覆盖映射

状态：**G1 已关闭（2026-10-23），G2 未关闭**。A01–A16 均有自动化、隔离 Chromium 或跨端 E2E 证据，逐条结论见文末「G1 收口」。隔离 Chromium 直接加载正式 Runtime 入口并使用真实 WebM/WAV/GLB；跨端 E2E 已运行远程 Renderer 默认海报、真实项目放映、双窗口、独立构建播放、有声导出隔离与临时开启的指定状态捕获。MCP 自 2026-10-23 起移出本轮验证与发布范围；跨端混版、生产裁剪镜像最终重建、修正版 30 分钟长测与 B01–B08 模型基准仍属 G2，见 [G2 遗留清单](./g2-followups.md)。

一句话结论：A01–A16 均有真实浏览器或跨端证据；A04 的残留是 Three.js 库层对渲染器的保留，已转 G2，不影响该场景的功能隔离结论。

## 阅读顺序

| 需要 | 位置 |
| :--- | :--- |
| 当前结论：G1 是否关闭、A01–A16 逐条证据 | [G1 收口（2026-10-23）](#g1-收口2026-10-23) |
| A04 100 次挂载保留堆的根因与边界 | [A04 保留堆结论](#a04-保留堆结论) |
| 首批自动化与隔离浏览器细节 | 下文「首批结论」「逐条映射」「第二批」 |
| 跨端 E2E、临时捕获与 CLI 链路 | 下文「第三批」「第四批」 |
| 历史长测与修正版短测 | 下文「长时资源采样」 |

下文按时间保留各批证据；有冲突时以文末「G1 收口」的逐条结论为准。

## 首批结论（A01/A02/A05/A14）

下表是首批结论；A01–A16 的最终收口见文末「G1 收口」。

| 编号 | 场景 | 本轮结论 | 仍需人工/浏览器 |
| :--- | :--- | :--- | :--- |
| A01 | Schema、标签和前后依赖 | 六类错误均有 `trackId`/`fieldPath` 断言；本轮补齐未知字段拒绝 | 无 |
| A02 | 生命周期与乱序回执 | 迟到 play、旧 revision 定位、卸载后迟到失败、快速换页四类有断言；本轮修复 tick 跨 revision 提交 | 换页在真实放映过渡中的表现 |
| A05 | 资源替换 | 签名/索引失效明确报错；资源替换刷新身份；模型缓存按文件哈希分区；跨端图片替换后新预览 URL 和实际像素由红转蓝 | 三维动作资源真实替换后的旧引用失效链路 |
| A14 | 指纹与发布 | 不同动作时刻生成不同任务与不同状态摘要；临时图不提升默认指针；图片失败不覆盖诊断；远程同时间点跨任务 PNG 逐像素相同 | 取消与迟到结果跨任务发布竞争 |

## 逐条映射

### A01 Schema、标签和前后依赖

要求：重复 id、缺失目标、依赖环、未知字段、无穷依赖和属性冲突有准确 `trackId`/`fieldPath`。

| 条款 | 证据 | 断言 |
| :--- | :--- | :--- |
| 重复 id | `runtime/src/core/motion/compile.test.ts` · 拒绝重复 id、非法数值与海报越界 | `fieldPath=timeline.tracks[1].id`、`trackId=title` |
| 缺失目标 | 同文件 · 拒绝循环依赖与缺失前驱 | `fieldPath=timeline.tracks[0].afterTrack` |
| 依赖环 | 同文件 · 拒绝循环依赖与缺失前驱 | `fieldPath=timeline.tracks[0].afterTrack`、`trackId=a` |
| 未知字段 | 同文件 · 拒绝未知字段并定位到具体层级与轨道 | 定义、轨道、`clip`、`poster` 四层各自定位到实际写错的键 |
| 无穷依赖 | 同文件 · 拒绝非有限依赖数值与无限重复并保留定位 | `startMs`/`offsetMs` 为 Infinity、`repeat` 无限、`durationMs` 为 NaN 均带定位 |
| 属性冲突 | 同文件 · 拒绝同一 DOM 目标上的重叠属性 | `trackId=b`、`fieldPath=timeline.tracks.b.properties` |

实现变更：`compile.ts` 新增字段白名单校验（定义、轨道按类型、`poster`、`clip`、`transform`）。值为 `undefined` 的键视为未声明，兼容展开语法。未知字段此前被静默忽略，`asset` 误写为 `assetName` 只表现为“没有动画”；现在直接返回 `TIMELINE_SCHEMA_INVALID` 并指向 `timeline.tracks[0].assetName`。

对应历史故障：工作空间 50 / 项目 139 / 页面 757 的旁白初始化失败。该用例在 `usePageTimeline.validation.test.ts` 的期望值同步改为实际写错的键。

### A02 生命周期与乱序回执

要求：快速换页、取消加载、旧 play/seek/frame 回执不提交到新 generation 或 revision。

| 条款 | 证据 | 断言 |
| :--- | :--- | :--- |
| 迟到 play 回执 | `transport.test.ts` · 暂停后迟到的 play 回执不留在播放集合，并再次暂停适配器 | 意图保持 `paused`，适配器被二次暂停，未进入播放集合 |
| 旧 revision 定位/frame 回执 | 同文件 · 旧 revision 的定位回执不提交位置或完成状态 | 位置停在 100ms，越过轨道末尾的 400ms 回执不污染 `completedTrackIds` |
| 取消加载/卸载 | 同文件 · 卸载后迟到的准备失败不把已释放会话改成错误 | 阶段保持 `disposed`，`errorCode` 为空 |
| 快速换页 | `usePageTimeline.presentation.test.ts` · 预览海报准备期间快速离页，不采样已释放的时间轴或上报迟到错误 | 不上报迟到错误 |
| generation 隔离 | `transport.test.ts` · 同一 generation 内独占目标并按代际失效 | 换代后旧占用与声明同时失效 |
| 重复释放 | 同文件 · dispose 后释放目标与适配器且不再提交状态 | 重复 `dispose` 幂等，`play` 返回 false |

实现变更：`transport.ts` 的 `tick()` 现在记录进入时的 `revision`，在 `requestApply`、`startAdapters` 与完成分支三处复核。此前一轮 tick 在等待 apply 回执期间若发生定位，回执返回后仍会继续推进，把旧位置和完成集合提交到新 revision。该缺陷由本轮新增用例稳定复现。

### A05 资源替换

| 条款 | 证据 | 断言 |
| :--- | :--- | :--- |
| 动作身份失效明确报错 | `model-adapter.test.ts` · 相同名称和时长的动作被替换后，旧签名明确失效 | `MODEL_ANIMATION_REFERENCE_STALE`，不按名称或时长放行 |
| 片段索引失效 | 同文件 · 片段索引失效时返回可定位的 stale 错误 | 明确 stale 错误，不回退到其它片段 |
| 合法替换刷新像素身份 | `backend/tests/unit/test_page_screenshot_fingerprint_service.py` · `test_screenshot_fingerprint_should_include_resource_identity` | 同名资源文件哈希变化生成新指纹，三维资源同样生效 |
| 动作签名语义稳定 | `animation-signatures.test.ts` · bufferView stride/padding 不影响相同动作的语义身份；HTTP 环境与 Backend SHA-256 对拍 | 相同动作跨环境一致 |
| 不读取历史文件兜底 | `model-cache.test.ts` · 应按 `fileHashOrUrl\|engineVersion\|validationProfile` 拼接；分区共享 | 文件哈希变化后不共享缓存条目，不复用历史解析结果 |

### A14 指纹与发布

| 条款 | 证据 | 断言 |
| :--- | :--- | :--- |
| 不同动作时间不复用同帧 | `backend/tests/api/test_external_screenshot_jobs.py` · `test_external_screenshot_job_identity_includes_motion_time` | 1200ms 与 1800ms 生成不同任务，同选择器才复用；选择器哈希参与去重 |
| 同上（运行时层） | `transport.test.ts` · 相同计划的指定状态采样摘要稳定且不启动播放 | 不同采样时刻得到不同 `stateDigest` |
| 临时 sample 不提升默认截图指针 | `test_external_screenshot_jobs.py` · `test_external_screenshot_job_status_and_content` | 任务成功后 `page.screenshot_storage_key` 仍为空 |
| 诊断成功不被图片失败覆盖 | `backend/tests/unit/test_validation_screenshot_cache.py` · `test_missing_image_does_not_rerun_validation` | 图片读取失败只返回 `None`，诊断结果与缓存命中保持不变，不重开浏览器 |
| 能力关闭时明确拒绝 | `test_external_screenshot_jobs.py` · `test_external_screenshot_job_rejects_closed_timeline_capability` | 返回 409 `TIMELINE_UNSUPPORTED`，不落任务 |

## 实测命令与结果（2026-10-22）

| 命令 | 结果 |
| :--- | :--- |
| `pnpm --filter web-runtime-vue exec vitest run src/core/motion src/runtime-kit/public/composables/motion` | 12 files / 83 passed |
| `pnpm --filter web-runtime-vue test` | 166 files / 1342 passed / 3 skipped；1 个既有 Windows 临时目录 `EBUSY` 失败 |
| 单独复跑 `vitest run src/core/plugins/runtime-build-worker.test.ts` | 32 passed（确认上一项为并行运行下的临时目录锁，不是本次改动） |
| `pnpm --filter web-runtime-vue check` | `vue-tsc -b` 通过 |
| `uv run --project backend pytest ... test_slideshow_schema.py test_render_motion_dispatch.py test_page_screenshot_fingerprint_service.py test_validation_screenshot_cache.py test_external_screenshot_jobs.py test_system_timeline_capabilities.py test_runtime_kit_components.py -q` | 56 passed |

## 第二批：隔离 Chromium 真实资源场景

入口为[夹具说明](../../../../tests/experiments/motion-g1/README.md)。2026-10-22 在 Windows x64、Chromium 148.0.7778.96 上运行 `node tests/experiments/motion-g1/run.mjs`：**9/9 场景通过**，未处理页面异常为 0。基准 HEAD 为 `178b7697378a6d5e4db3acf9639e352e8a5e2bf8`，工作区含未提交改动；原始 JSON、逐场景截图、完整素材 SHA-256 保存在本地 `.tmp/motion-g1/`，不随仓库提交。固定视频、WAV、GLB 的 SHA-256 分别为 `97a29cc69cedb70bb1dfde3e4337b4588d5ee68fa793bd5107e682eda3f831a4`、`5227f916fed48c7f187a6864303ff243e9a79da3500c314b8c1f19f8a746d517`、`7a73fb2016dfdb70046c887879a4d1939698f7634c92eb36c0601809757b07eb`。

| 编号 | 浏览器断言与结果 | 结论边界 |
| :--- | :--- | :--- |
| A03 | 初态/入场/并行/错峰、乱序回到 300ms、reduced 可读；元素居中偏差 0px | 本地 DOM 布局通过 |
| A04 | 同 GLB 两实例在 500ms 的画面差异 15.71%；仅改变第二实例后第一实例差异 0、第二实例差异 1.46% | 真实 WebGL 实例隔离通过；相机配置组合仍待扩展 |
| A06 | 视频解码就绪后播放，逻辑/媒体时钟差约 5ms；稳态 `currentTime` 写入 0 次 | 本地视频主时钟通过 |
| A07 | 主视频与慢速次要 required 视频真实缓冲均冻结同步集合；用户暂停后不自行恢复；optional 音频真实加载失败后主视频和视觉继续。受控时钟验证 optional 准备、采样、播放、固化失败降级及 required 15 秒超时 | 本地媒体与失败降级通过；受保护跨端媒体仍待验证 |
| A08 | `navigator.userActivation` 全 false 的页面自主播放得到 `TIMELINE_MEDIA_BLOCKED`；点击后有声 WAV 实际推进 | 自动播放阻断与恢复通过；错误/超时展示未测 |
| A09 | 450ms/100ms 正反定位各写一次媒体时间；900ms 主媒体后视觉继续，最终完成并停媒体 | 静音视频定位与交接通过；有声拖动未测 |
| A10 | 旧媒体会话只收集 1 个独立音频，时间轴视频不计入；旧会话播放/暂停/释放不暂停或归零视频 | 本地旧/新所有权隔离通过 |
| A12 | 系统 reduced 得到可读静态视觉但旁白未静音且不提前完成；显式 full 覆盖系统偏好；capture 父作用域禁止媒体播放；追加验证系统 full 与显式 reduced，定向复测 1/1 通过 | 本地 system/显式偏好组合通过，跨端 Editor 控件仍待测 |
| A13 | 本地 poster、500ms 与标签偏移 900ms 的回执/视觉不同，视频暂停且 seek 完成；乱序返回与禁动画截图差异均为 0 像素。隔离 E2E 的远程 Renderer 补测 0ms、1800ms、标签与负偏移的真实 PNG 和 applied 回执 | DOM 远程指定状态链路通过；远程视频/骨骼素材仍待测 |

首轮失败保留在本地记录：视频端点没有实现 Range 导致 seek 等待超时；补 206/HEAD 后通过。WebGL 的 `toDataURL()` 因非保留 drawing buffer 得到空图，改用元素截图后比对。Playwright `evaluate` 会带用户激活，改由页面加载脚本自主触发无手势播放；这三处均为夹具取证修正。浏览器过程还暴露正式 `transport` 在位置与 phase 未变时漏发 `intent` 的缺陷；新增意图对比和订阅回归，播放/暂停状态通知现在与真实媒体一致。

后续 A07 复核发现原 transport 只检测主媒体缓冲，次要 required 媒体无法冻结同步集合；现检查全部活动 required 媒体、冻结时暂停所有适配器、optional 卡顿跳过同步采样，并为持续缓冲增加 15 秒有界错误。受控时钟测试 15/15 通过，真实主媒体缓冲浏览器回归 9/9 通过；Runtime 全量 167 files / 1346 passed / 3 skipped，类型检查与 `vite build` 通过（5478 模块）。尝试用慢速 WAV 复现次要媒体真实缓冲时，浏览器在 `prepare()` 阶段已经加载完成，未出现目标状态；该试验不能作为次要媒体浏览器通过证据，仍待设计能在准备后触发真实缓冲的夹具。

Runtime 定向单测 3 files / 26 passed、全量 167 files / 1344 passed / 3 skipped、`vue-tsc -b` 与本轮修改文件 ESLint 通过；正式 `vite build` 成功（5478 模块，保留大 chunk 与插件耗时提示）。这只证明开发依赖下构建成功，不证明裁剪后的生产镜像或独立产物运行。仓库契约 8 files / 63 passed。

## 第三批：隔离 E2E 跨端链路

2026-10-22 使用测试专用本地 PostgreSQL/Redis，`prepare-e2e.mjs --stop-services` 重置并播种独立 `_e2e` 数据，启动 Backend、Editor、Runtime、Renderer；未改动开发数据库。之后直接运行 Playwright，不再次准备或重置环境。

| 命令 | 结果与边界 |
| :--- | :--- |
| `playwright test --project=smoke page-screenshot.spec.ts` | 2/2 通过：真实 Backend→Renderer→Runtime 生成可下载 PNG，GLB 页面含真实红色模型像素。属于默认静态截图，不代表指定状态捕获。 |
| `playwright test --project=smoke motion-playback.spec.ts` | 正式项目预览的短时间轴完成后推进一次；动效页的 manual 保持等待并可手动翻页、timer 定时推进、无媒体的 media_end 走停留时间兜底；无时间轴页明确报错；指定状态截图默认返回 409 `TIMELINE_UNSUPPORTED`；动效页 PPTX/PDF 导出前后静态海报逐字节一致；远程 Renderer 默认截图包含海报红色标题像素。另补独立构建后的时间轴播放与静态 PDF 下载。auth + smoke 完整回归 **22/22 通过**。 |
| `playwright test --project=smoke motion-playback.spec.ts --grep "截图 PDF"` | 1/1 通过：截图 PDF 为可下载的真实 `%PDF-` 文件，导出前后时间轴页静态海报逐字节一致。首次因测试直接点击被标签覆盖的隐藏单选框失败，改为点击可见选项后通过。 |
| `playwright test --project=smoke motion-presenter.spec.ts` | 2/2 通过：真实双窗口中控制台缩略图与观众放映的执行策略分别为 `thumbnail`/`presentation`；观众全屏与控制台翻页同步，重复打开复用同一观众窗口；观众页时间轴播放、暂停、继续改变真实 DOM 透明度，控制台海报始终保持静态。追加关闭观众窗口后重开、控制台晚到重载并恢复全屏/翻页同步，定向 1/1 通过。 |
| `playwright test --project=smoke page-export.spec.ts` | 1/1 通过：普通页面导出真实 PPTX 文件。 |
| `playwright test --project=auth --project=smoke` | 最终 20/20 通过：新增十例与既有登录、资源、组件、构建、预览、截图和导出流程并行运行。 |

新用例位于 `tests/e2e/specs/smoke/motion-playback.spec.ts` 和 `motion-presenter.spec.ts`。首次运行时一个定位器同时匹配导航缩略图和当前画布，属于测试定位错误；限定到 `.page-content-wrapper` 后通过。导出用例初次运行暴露素材没有声明海报位置，预览正确停在零点透明初态；补 `poster.atMs=1800` 后通过。PPTX 用例已验证产物容器、幻灯片条目和导出前后海报画面一致，未检查 PPTX 内部该标题的可编辑文本；PDF 用例验证文件头、大小与导出前后画面一致，未解析 PDF 像素。两者均未覆盖有声媒体或放映中导出。远程 PNG 用例通过像素验证海报可见，仍属于默认静态截图。双窗口用例覆盖 A16 的基本唯一播放者、同步、观众关闭重开及存活观众前的控制台重载；旧协议命令仍待跨窗口实测，协议单测已覆盖旧 owner 与旧 revision 的拒绝。G1/G2 保持未关闭。

独立构建用例先在放映模式下寻找被隐藏的导出按钮而失败；退出放映后完成真实构建产物的播放及 `%PDF-` 下载，定向 1/1、随后 auth + smoke 22/22 通过。此证据验证构建输出脱离开发服务器运行，仍未证明音视频、GLB 在独立产物内的完整素材交接。

### 临时开启能力的指定状态远程截图

保持正式 `TIMELINE_CAPTURE_SNAPSHOT_ENABLED=False`；仅在独立 `_e2e` Backend 进程通过本地测试入口开启，测试后已停掉该进程。`MOTION_CAPTURE_TEST_OPT_IN=1` 运行 `runtime-heavy/motion-capture-opt-in.spec.ts` **1/1 通过**：真实 Renderer 对同一页面生成默认 poster、0ms、1800ms、`readable` 标签及 `readable-300ms` 五张 PNG；零点红色标题像素几乎为零，1800ms 可见，标签与 1800ms 像素比例一致，负偏移回执 `sampled_time_ms=1500` 且红色像素少于 1800ms。1800ms/标签回执 `applied_motion.status=applied`，不同时间获得不同 Job，四张临时结果未改写页面默认截图 URL。首次未含标签/偏移版 1/1 通过，扩展后再次 1/1 通过；PNG 证据保留在本地 Playwright 附件目录。

## 第四批：G2 CLI 真实链路与客户端契约

本机 `wp` 0.3.5 已安装且 `local` Profile 配有开发 PAT。运行 E2E 时，8000 端口为独立 `_e2e` Backend，开发 PAT 对该服务返回 `UNAUTHENTICATED`；这不是 PAT 本身失效。最初在受限沙箱内对开发 PostgreSQL `192.168.31.204:55432` 和 Redis `192.168.31.204:6379` 的 TCP 探测误报不可达；提高到实际服务权限后两者均连通。E2E 测试使用同版本 CLI 源码入口和一次性 Profile/PAT，未读取或改写用户现有 CLI 配置。

| 验证 | 结果与边界 |
| :--- | :--- |
| CLI 定向测试 `test_project_slideshow.py test_screenshot_command.py test_capability_commands.py` | 42 passed。 |
| CLI→E2E Backend/Runtime/Renderer | 通过：`whoami`、时间轴能力、版本化 Runtime Kit、项目创建、页面 Mutation Job 创建并等待成功、源码结构化编辑并等待成功、版本从 1 到 2、路由、预览、默认远程截图 PNG 下载（22321 bytes）、指定状态截图关闭能力错误。隔离项目 58/页面 77 已归档，临时 PAT 已吊销；一轮早期尝试因测试 PAT 少 `preview:run` 被拒，补权限后通过。 |
| MCP 定向测试 `test_motion_screenshot_tools.py` | Backend 从 External API 操作注册表向实际 OpenAPI 路由生成 `x-wp-operation v1` 后，4/4 通过；MCP 契约检查通过 78 bindings / 73 routes。MCP 完整契约套件为 228 passed / 9 个此前已记录的跨仓基线失败，不能算作全套通过。见 [WP11 客户端工作包](./work-packages/wp11-agents-clients.md)。 |
| 当前源码 Runtime 生产镜像 `docker build -f runtime/Dockerfile` | 构建成功；Docker Hub 元数据请求先遇 EOF，给已缓存且架构匹配的 Node 基础镜像补本地标准 tag 后以 `--pull=false` 离线继续。临时 `RUNTIME_ROLE=preview` 容器实际启动并达到 Docker `healthy`，`/__runtime_healthz` 与 `/__runtime_readyz` 均返回 `ok`，`runtime_kit_version=1.0.0`、相同 `build_id=sha256-554a2412a97a4795ba7b25ea7159a38d8d12f12f3a9e98257ba2232996484e84`；镜像内保留 Vite、已裁剪 `vue-tsc`。临时容器已停止。仅验证 preview 角色启动，不代替 build/check 角色、独立构建播放或静态导出。 |
| 现有开发 `local` CLI Profile | 停止已完成的 E2E 四项应用服务并恢复开发 Backend 后，`wp --profile local whoami` 返回管理员身份；`doctor` 的 Backend、数据库、Redis、OpenAPI、PAT、27 个授权工作空间及默认工作空间 44 全部正常。开发 Runtime、Editor、Renderer 也已恢复并通过状态探针。 |

OpenAPI 生成物已同步到 Editor，`test:contracts:generated` 通过；Backend 的操作元数据回归 2/2、连同 External API 回归 13/13 通过。开发 Backend 热重载在源码变更后停留于 shutdown，按 `dev-start-test` 预演与停服脚本重启为无 reload 进程后恢复；在线 `/openapi.json` 已返回 `page.get` 的 v1 元数据。生产镜像 `build` 角色缺凭证/Backend 地址时按设计拒绝启动。启动期发现 Mermaid 测量会在生产运行时加载 `jsdom`，而旧镜像裁剪了开发依赖；将它移入生产依赖并重建后，同一 `build_id=sha256-498704f8e25aae432791414c2e36862fbff3c2d937ef0fe1fe129612f898af42` 的 `preview`、`check`、配置测试专用凭证及空闲 Backend 地址的 `build` 三角色均实际启动并就绪，裁剪容器中的正式 `measureMermaidAspectRatio('graph TD;A-->B;')` 返回有效比例 `0.5783`，对应 Runtime 单测 7/7 通过。该镜像构建早于后续 A07 transport 修复，最终 G2 门禁须以最终源码重建并复核；构建 Worker 本次只验证配置与启动，不代表已领取真实构建任务。

隔离 E2E CLI 链路验证了创建和写入流程；开发 `local` Profile 目前验证到连接、身份、权限及服务健康，尚未在开发数据中重复写入测试页面。这两组证据均不等于内置助手或 MCP 完整创作基准。

## 历史未覆盖项状态（2026-10-23）

- A15：已完成有声 PNG/PDF/PPTX 导出隔离、导出完成与取消不改变主放映状态、PDF 内嵌图像姿态、PPTX 可编辑文本与姿态透明度。边界：导出使用静态海报姿态，不覆盖放映中逐帧视频导出。
- A07：受保护音视频的 HEAD/Range/无票据拒绝与视频 seek 已完成；optional 音频真实加载失败与 `degraded` 回执已完成。边界：真实缓冲只在本地慢速夹具复现，受保护媒体的网络缓冲未单独复现。
- A05：三维动作资源真实替换后旧签名失效已完成；图片替换后的受保护预览 URL 与像素身份已完成。
- A13：受保护视频帧与真实骨骼 GLB 帧已完成；受保护音频不产生像素，未单独纳入。正式捕获开关仍关闭，opt-in 只在临时 E2E 入口验证。
- A14：同时间点跨任务逐像素一致、取消后的迟到结果不覆盖较新截图均已完成；诊断成功不被图片失败覆盖有单测。
- 性能/规模：A04 挂载保留堆已定位到 Three.js r186 模块级 DFG LUT 的渲染器持有，另行记录；修正版 30 分钟长测、暂停响应与温缓存定位未运行，归 G2。

## 追加复测：A04、A07、A09（2026-10-22）

历史段落中的 9/9 与「次要缓冲未复现」记录的是第一批结果。其后补充慢速次要 required 视频、真实加载失败的 optional 音频，以及有声媒体连续正反定位，并扩展 A04 显式相机隔离。完整 `node tests/experiments/motion-g1/run.mjs` 最终 **12/12 通过**，未处理页面异常为 0；A04 与 A09 新断言也各自定向通过。次要视频缓冲时，主视频实际暂停且同步位置冻结；optional 音频网络加载失败后，主视频和视觉继续。相机配置仅改变第二 GLB 实例画面，第一实例逐像素比较差异仍在容许范围。有声音频连续定位到 1400→250→1100ms 期间保持未静音、暂停，真实 `play()` 调用次数为 0。

transport 同时修复 optional 轨道在准备、采样、播放或固化失败时误将整页置为 error 的缺陷：失败轨道只释放一次，其余 required 轨道继续；required 准备失败仍报错。`transport.test.ts` **20/20 通过**，Runtime `vue-tsc -b` 通过。此处仅关闭本地 Runtime 对应子断言；正式跨端受保护音视频、UI 错误展示、远程视频/骨骼帧及 G2 门禁仍未关闭。

## 追加跨端验证（2026-10-23）

- 独立 `_e2e` 的 auth + smoke 扩展全套 **27/27 通过**；新增真实 WAV `media_end` 双页循环、required 媒体加载错误和 15 秒超时 UI、Editor system/reduced/full 控制与定位、旧协议和旧 owner 拒绝、受保护音视频 HEAD/Range/无票据拒绝与视频 seek。资源替换用例另定向 **1/1 通过**：上传纯色 SVG，合法替换后新的 artifact 使用新文件 hash，实际截图由红转蓝。
- 指定状态 opt-in 用例：DOM 海报/0ms/1800ms/标签/负偏移与同一 1800ms 跨任务逐像素一致 **1/1**；受保护 WebM 在 0ms 与 900ms 真实帧像素不同、重复 900ms 摘要和像素相同 **1/1**；真正含 `skin`、`JOINTS_0`、`WEIGHTS_0`、joint 动画的 GLB 在 0ms 与 1000ms 远程 PNG 中红色几何水平重心显著移动 **1/1**。三项均通过 Backend→Renderer→Runtime，默认能力开关未修改。
- Runtime optional 轨道失败后的捕获桥返回 `degraded`，不伪报 `applied`；定向 transport/capture/integration **30/30**、类型检查通过。完整 Runtime 单测首次复跑为 166 文件通过、1 个 Mermaid 测量超时（1351 passed / 3 skipped），该测例独立重跑 **7/7** 通过；仍需无并发负载下复跑完整门禁。

## 长时资源采样（原始运行：2026-10-22T19:49Z）

原始本地结果保存在 `.tmp/motion-g1/soak-result-original.json`，目标 1,800,000ms，实际 1,804,142ms（30分04秒），Chromium 148.0.7778.96；随后循环播放 423 次。运行期间 `errors=[]`，记录的最大时钟漂移为 17.415ms。后来复核发现原脚本挂载阶段只等待时间轴 API ready，未等待两个 GLB 模型 ready，也未在卸载后等待绘制帧；因此该运行不能作为 100 次完整模型挂载/卸载的清理验收，30 分钟播放循环与漂移数据仍是历史播放证据。

堆数据由 CDP `HeapProfiler.collectGarbage` 后采集。初始页面为 3.723 MiB；挂载循环第 10/20/30/40/50/60/70/80/90/100 次后分别为 13.008/14.690/16.299/16.308/17.480/18.700/19.956/21.123/22.290/23.436 MiB，末尾相对初始增加 19.713 MiB。对应 DOM 节点数从基线 25 增至 142/262/382，第 40 次降至 102，之后升至第 100 次的 222；100 次后 canvas 为 0、活跃 WebGL context 为 0。播放阶段每轮重启 3 秒时间轴并每约 3.15 秒采样，20 次循环时堆为 23.682 MiB，此后采样范围 23.678–23.772 MiB（跨度 0.094 MiB），结束时 23.768 MiB；节点数固定为 374、监听器 23、媒体元素 1、活跃 WebGL context 与 canvas 均为 0，RAF 为 1、interval 为 1，timeout 在 0/1 间变化。浏览器、Renderer、GPU、NetworkService 进程计数全程各为 1。最终卸载后媒体、canvas、活跃 WebGL context 和 timeout 均为 0；节点数 222、监听器 18、RAF 1、interval 1。初始 RAF/interval 也是 1/1，因此这些常驻计数未高于页面基线。

夹具已清空卸载句柄、清理已回收或已丢失 context 的弱引用，并以标量累计创建数。首轮短测未等待 A04 两模型 ready，且在卸载后立即采样；其 A04 堆数不作为完整模型生命周期证据。随后补充每轮双模型 ready 检查，并在卸载后等待两个绘制帧，再比较真实 Vite dev server 与 `vite build()` + `vite preview()`。`MOTION_SOAK_MS=1000`，每组均为 100 次挂载/卸载、1 次播放循环、Chromium 148.0.7778.96、`errors=[]`：

| 构建模式与场景 | 基线 heap | 第 10 次 heap / nodes | 第 100 次 heap / nodes | 其他清理证据 |
| :--- | ---: | ---: | ---: | :--- |
| development · A03 DOM | 3.72 MiB | 4.62 MiB / 132 | 4.68 MiB / 22 | 第 100 次前的临时高点回落；无 WebGL context/canvas |
| production · A03 DOM | 1.37 MiB | 2.07 MiB / 22 | 2.21 MiB / 22 | 第 10 次后 heap 增量收敛；无 WebGL context/canvas |
| development · A04 双模型 | 3.72 MiB | 13.02 MiB / 142 | 23.33 MiB / 222 | 200 个模型实例均 ready；创建 context 200，活跃 context/canvas 为 0 |
| production · A04 双模型 | 1.37 MiB | 5.64 MiB / 45 | 15.68 MiB / 225 | 200 个模型实例均 ready；创建 context 200，活跃 context/canvas 为 0 |

A04 第 10 到第 100 次强制 GC heap 增量分别为 development **10.31 MiB**、production **10.04 MiB**；生产构建仍有显著 heap 与 DOM 节点增长，所以不能把该趋势归因成开发服务器独有的假阳性。A03 的开发模式节点高点在增加卸载后两帧等待后回落，而 production 的节点数从第 10 到第 100 次保持 22，支持原 A03 即时采样受开发模式/卸载时序影响。当前证据只能定位到真实 A04 重复加载后的保留堆/DOM 信号，尚不能区分 Runtime 泄漏、Three.js/GLTF 缓存或其它延迟回收；活跃 WebGL context/canvas 为 0 只证明这两类资源计数已清空。

原长测每轮重启 3 秒时间轴并每约 3.15 秒采样，测到的是循环播放和短暂停顿，不代表无缝连续 30 分钟；堆是页面 JS heap，未覆盖浏览器/GPU 原生内存。脚本没有统计 dropped-frame 计数，因此时钟漂移和 readyState 采样不能证明播放过程中完全无卡顿。仍需调查 A04 的保留堆/DOM，并在修正版脚本下复跑完整 soak，才能判断清理门槛。长测指标和有限样本不构成 G1/G2 完成证据。

## G1 收口（2026-10-23）

当次复跑：`node tests/experiments/motion-g1/run.mjs` **12/12 场景通过**（Chromium 148.0.7778.96，未处理页面异常 0）；`vitest run src/core/motion src/runtime-kit/public/composables/motion` **12 files / 93 passed**。跨端证据沿用同一独立 `_e2e` 环境当日的 auth + smoke **27/27**、定向导出/替换/演讲者/捕获用例及临时 opt-in 捕获用例。

| 编号 | 场景 | 证据 | 边界 |
| :--- | :--- | :--- | :--- |
| A01 | Schema、标签和前后依赖 | `compile.test.ts` 六类错误均断言 `trackId`/`fieldPath`；本轮无回归 | 无 |
| A02 | 生命周期与乱序回执 | `transport.test.ts` 迟到 play、旧 revision、卸载后迟到失败、同代际失效；`usePageTimeline.presentation.test.ts` 快速离页；E2E `motion-playback.spec.ts` 真实双页 `media_end` 循环 | 未做高频人工连点换页的帧级统计 |
| A03 | DOM 和布局 | 隔离 A03：入场/并行/错峰/乱序/`reduced`，居中偏差 0px；生产 100 次进出节点稳定为 22 | 无 |
| A04 | 同一模型两个实例 | 隔离 A04：同刻双实例画面差异、单实例修改隔离、显式相机只影响第二实例；100 次双 GLB 挂载每轮均 ready，活跃 context/canvas 为 0 | 保留堆根因见下；不作为 A04 功能失败 |
| A05 | 资源替换 | `model-adapter.test.ts`/`model-cache.test.ts`；后端指纹；E2E 图片替换后新预览 URL 与红转蓝像素；三维替换后旧动作签名失效 | 无 |
| A06 | 媒体准备与时钟 | 隔离 A06 解码就绪后播放、时钟差约 5ms、稳态不逐帧写 `currentTime`；E2E 真实 WAV `media_end` 双页循环 | 无 |
| A07 | 缓冲与用户暂停 | 隔离 A07 主/次要 required 真实缓冲、用户暂停不自动恢复、optional 失败降级；E2E 必需媒体错误/15 秒超时 UI、受保护音视频 HEAD/Range/无票据与视频 seek、optional 捕获 `degraded` | 受保护媒体网络缓冲未单独复现 |
| A08 | 手势与失败 | 隔离 A08 无手势自动播放 `TIMELINE_MEDIA_BLOCKED`、点击恢复；E2E 错误/超时可见且有界 | 无 |
| A09 | seek 与主媒体交接 | 隔离 A09 正反定位、媒体结束视觉继续；有声连续定位 `play()` 为 0 | 无 |
| A10 | 旧媒体与新所有权 | 隔离 A10 旧会话不暂停/归零时间轴视频、不计入完成；E2E 演讲者唯一观众播放器 | 无 |
| A11 | 放映与推进 | E2E manual/timer/`media_end`/`timeline_end`、无时间轴明确报错、构建产物播放 | 无 |
| A12 | 偏好与静态状态 | 隔离 A12 system/reduced/full 与静态可读、不误静音/完成；E2E Editor 预览控件与定位 | 无 |
| A13 | 指定状态捕获 | 隔离 A13 poster/时间点/标签/负偏移、乱序逐像素一致；远程 opt-in DOM、受保护视频 0/900ms、骨骼 GLB 0/1000ms | 受保护音频不产生像素，未单独纳入；正式开关仍关闭 |
| A14 | 指纹与发布 | 后端同时间点不同任务、临时图不提升默认指针、诊断不被图片失败覆盖；跨任务取消后迟到结果不覆盖较新截图；远程同时间点逐像素一致 | 无 |
| A15 | 导出隔离 | E2E 有声 PNG/PDF/PPTX 静音与海报姿态、PPTX 可编辑文本与 alpha、PDF 3840x2160 内嵌像素、导出完成与取消均保持主时间轴播放与未静音；opt-in 6000ms 指定姿态 PNG | 导出为静态姿态，不覆盖逐帧视频导出 |
| A16 | 演讲者模式 | E2E 双窗口唯一播放者、同步、重开、控制台晚到、旧协议/旧 owner 拒绝；单测旧 owner/revision | 无 |

### A04 保留堆结论

100 次进出的保留堆不是应用闭包持有渲染器：最小复现证明，Three.js 上传过的共享纹理会在自身注册 `dispose` 监听，而该监听捕获渲染器；纹理存活期间渲染器及其内部程序缓存无法回收。Three.js r186 的 PBR 路径使用模块级 DFG LUT（`getDFGLUT()` 的 16×16 `DataTexture`），该纹理不会释放，所以每个使用 `MeshStandardMaterial` 的渲染器都会被它保留。最小复现中 20 个渲染器全部存活，释放共享纹理后全部归零；仅共享几何不产生该保留。修复会涉及 Three.js 内部或逐实例纹理克隆，超出 G1 功能收口范围，记为 G2 的性能/清理后续项。实际卸载后 DOM canvas、活跃 WebGL context、媒体、RAF 与计时器均为 0，A04 功能隔离不受影响。
