# WP12 联合验收与能力开放

状态：待验收（自动化复核与文档收口完成；G1/G2 真实浏览器、远程 Renderer 与模型基准未执行，能力保持关闭）。主责：联调 / 发布。前置：WP01–WP11 全部交付并可复核。

## 输入

依据 [验收计划](../acceptance.md) 复核 G0 决策、A01–A16、B01–B08，以及 [运行契约](../runtime-contract.md) 的版本/所有权/身份要求。单元测试和工作包勾选不能替代真实浏览器、远程 Renderer 与客户端证据。

## 交付

- 验收完整案例：真实资源与动作查询 → Vue 编排 → 标题/旁白/模型/视频同步 → 暂停定位重播 → timeline_end → 默认与指定状态静态交付。
- 执行真实跨域、媒体 HEAD/Range、有声自动播放受阻、缓冲与双窗口唯一播放者验证。
- 在生产依赖裁剪镜像、独立构建和支持浏览器上执行回归，核对资源、Schema/协议与 Runtime 发布身份。
- 完成模型八任务基准、100 次进出清理和至少 30 分钟受控循环，保留原始指标与失败修正记录。
- 验证灰度、混版派发与回退：旧内容继续运行，新请求不被旧 Worker 丢字段执行。
- 满足 G2 后才开放 capability、Runtime Kit 推荐、新推进模式和模型说明；同步用户文档、顶层 README 与发布清单中的实际支持范围。

## 发布出口

所有 required 场景通过，临时 sample 不污染默认截图、主放映状态或其它实例；Backend 不运行浏览器，Renderer 任务与浏览器进程/槽位/临时文件完整释放。

Firefox/WebKit、移动端或特定编码未完成验收时在支持矩阵中列明，不对外宣称已支持。跨页 BGM、复杂混音、动作混合、相机轨道、可视化时间轴和离线视频导出仍属于后续工作，不在首期关闭项中虚标。

## 实施记录

- G0/G1/G2 结论与代码版本：
  - G0 功能选型通过（WP01）；本轮未重新比较性能。
  - G1 未关闭：WP04–WP10 的单元、契约与构建证据已复核，但 A01–A16 中真实浏览器、跨域 iframe、双窗口、媒体 HEAD/Range、autoplay 受阻、WebGL 与指定状态捕获未执行。
  - G2 未关闭：Editor 真实交互、内置助手/CLI/MCP 同工作空间联合验收、真实 Backend → Renderer → Runtime、生产依赖裁剪镜像、混版派发、30 分钟受控循环与八任务模型基准均未执行。
  - 能力保持关闭：`TIMELINE_CAPABILITY_ENABLED=False`、`TIMELINE_CAPTURE_SNAPSHOT_ENABLED=False`，`SLIDESHOW_EXECUTABLE_ADVANCE_MODES` 不含 `timeline_end`；未向用户文档、顶层 README 或发布清单声明已支持。
  - 本地提交版本：主仓 WP11 `77e2c13`、CLI `0.3.5` `e5a3c3e`、MCP `0.1.0` `e84a016`；均未推送。
- 实际命令与结果（2026-10-21，本机未启动平台服务）：
  - Runtime 运动/入口/manifest：`pnpm --filter web-runtime-vue exec vitest run src/core/motion src/runtime-kit/public/composables/motion/usePageTimeline.v1.test.ts src/runtime-kit/public/components/assets/assets-v2.test.ts src/runtime-kit/manifest/runtime-kit.manifest.test.ts` → 10 files / 72 passed。
  - Editor 预览与放映表单：`pnpm --filter editor exec vitest run ...` → 5 files / 20 passed。
  - Backend 放映、时间轴能力与 Runtime Kit：`uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_slideshow_schema.py backend/tests/unit/test_slideshow_storage_schema.py backend/tests/api/test_system_timeline_capabilities.py backend/tests/api/test_system_slideshow_capabilities.py backend/tests/api/test_project_slideshow_settings.py backend/tests/api/test_project_route_slideshow.py backend/tests/api/test_external_project_slideshow.py backend/tests/contracts/test_runtime_module_policy.py backend/tests/contracts/test_runtime_kit_components.py -q` → 73 passed。
  - 渲染契约与 Renderer：render-contracts 30 passed；`renderer/tests/test_motion_capture.py renderer/tests/test_static_capture.py` 12 passed。
  - WP11 客户端链路：Backend 截图/迁移 33 passed、External API 13 passed；CLI 180 passed；MCP motion 4 passed、完整套件 319 passed/9 个既有跨仓基线失败；契约检查 78 bindings / 73 routes；生成漂移 paths=269、schemas=368 一致。
- 支持矩阵、未覆盖项与回退演练：
  - 桌面 Chromium 是首期发布基线，但尚未在目标浏览器与生产裁剪镜像执行；Firefox/WebKit、移动端、直播、第三方 iframe、跨页 BGM、复杂混音、动作混合、相机轨道、可视化时间轴与离线视频导出不列入支持范围。
  - 暂停响应、同步漂移、温缓存定位、确定采样、64 轨道/32 目标/30 分钟规模与 100 次进出清理指标未采集；G0 的性能后置不免除 G2 复测。
  - 回退演练未执行。当前没有用户可见开放，回退即维持 flags=false 且不发布新客户端；开放后必须验证旧 v1 内容、旧 Runtime、旧 Worker 与混版派发的明确失败或降级路径。
- 能力开放时间及文档版本：未开放，无承诺日期；必须先补齐 G1/G2 真实证据并完成 WP10 的生产裁剪入口加载验证。

## 2026-10-21 实施评审修复

本轮在主仓 `a6e865a` 基线上修复九项实现问题，保持能力关闭，未将局部回归记作 G1/G2 通过。

| 问题 | 修复与回归 |
| :--- | :--- |
| 默认入口偏离 G0，只有 JSON 视觉轨道 | `usePageTimeline.v1` 接入 `define`、有限资源 builder 与受控 GSAP 原生视觉；覆盖标签、错峰、函数复用、纯视觉与释放 |
| Runtime 捕获回执字段与 Renderer 不一致 | 在执行器边界将 camelCase 转换为控制协议 snake_case；Renderer 使用真实桥接形状测试 |
| 放映宿主只读包装根，遗漏页面句柄 | 在宿主范围内发现页面句柄；宿主测试将句柄挂到内层 SFC 根 |
| 延后媒体提前播放、到点不启动 | 仅在轨道有效区间播放；覆盖暂停、定位、恢复与结束后暂停 |
| 指定 full 采样实际仍用 reduced | 将采样模式传入所有适配器，不修改会话偏好；核对回执与实际中间态 |
| 同元素同属性永久独占 | 属性所有权按时间区间登记，允许非重叠入场/出场；覆盖间隙及乱序定位 |
| 主媒体交接后重播仍走墙钟 | 定位时复位交接状态，重播重新读取媒体时钟及缓冲状态 |
| 动作引用未校验语义签名 | 从实际 GLB accessor 字节重建 v2 签名，与 Backend 共享 LINEAR/STEP/CUBICSPLINE 夹具；同名同时长内容变化也拒绝旧引用 |
| 挂载计数污染计划身份 | 元素绑定改为 root 内稳定 key，视觉使用稳定结构路径；重复挂载的计划与采样摘要一致 |

动作签名同时覆盖普通 HTTP 缺少 SubtleCrypto 的环境；回退计算与标准 SHA-256 多分组/填充边界对拍。

本轮证据：

- Runtime 全量：165 files，1314 passed / 3 skipped；随后补充 HTTP 签名回归，motion/宿主/入口/签名定向 12 files / 106 passed。
- Runtime 正式 `build`（含 `vue-tsc -b`）通过；保留已有大 chunk 与插件耗时提示。
- 本轮新增 Runtime 模块与测试的 ESLint 检查通过；最终原生视觉摘要整理后，3 项原生视觉回归再次通过。
- Backend 模型 GLB、Runtime Kit 与模块边界：86 passed。
- 仓库文档、环境与开发工具契约：8 files / 63 passed。
- Renderer 全套与 render-contracts：75 passed；合跑配置有既有 pytest marker 和 Windows subprocess 清理提示，退出码为 0。
- [隔离 Chromium 回归](../../../../../tests/experiments/motion-regression/README.md)：`node tests/experiments/motion-regression/run.mjs` 通过，Chromium `148.0.7778.96`。真实视频延后播放/暂停/定位/重播/完成、full 250ms 采样 opacity=0.5、三个真实 GLB 签名及卸载通过，未处理页面异常为 0。开发脚本首次曾等待完成超时，随后两次复跑及保存后的脚本均通过；保留此记录，不作为稳定性门禁已完成的证据。
- 截图和 JSON 回执保存在本地 `.tmp/motion-fix-browser/`，构建日志为 `.tmp/motion-fix-build.log`；二进制、缓存和构建产物不入库。

本轮未运行完整 E2E、真实远程 Renderer 链路、双窗口、跨域票据/HEAD/Range、生产裁剪镜像、100 次进出、30 分钟循环、Firefox/WebKit 或 G2 模型八任务基准。平台服务及配置的远程基础依赖探测不可达，本轮使用隔离浏览器且未启动平台服务、未重置数据；这些验收仍是开放前置。

### 本地人工试用准备

用户随后明确选择“使用新 motion，允许准备本地内测入口”，要求三个项目外 Luna 新会话在 20261021-1/2/3 工作空间创作业务产物，由用户自行验收。该授权用于本地试用，不改变 G1/G2 结论。

本地 `.tmp/motion-local-trial/local_motion_trial.py` 启动入口要求 `WP_LOCAL_MOTION_TRIAL=1`，仅对该 Backend 进程启用 timeline、指定状态捕获、timeline_end 并在内存能力目录披露四个内部入口；正式源码常量与 Runtime manifest 仍默认关闭。恢复普通 `app.main:app` 启动入口即撤销本地披露。该目录不入库、不随镜像交付。

创作规范更新为资源 builder + 原生视觉；CLI 从最新开发源码重装，全局 Skill 更新至包含 Motion 创作说明的 1.4.5。未开展 G1/G2 或代替用户作成品验收。

首轮三个创作会话均反馈能力已启用但入口随后不可见。定位到临时启动入口只修改缓存清单，而 `load_runtime_kit_manifest` 的单项 LRU 缓存会因无参、显式 None 等调用方式切换被淘汰，后续从磁盘重读关闭值。已改为本地加载包装器在每次加载后对副本应用内测披露，不再依赖某一缓存对象存活；正式 manifest 文件不变。该问题属于本地试用准备错误，不记作模型创作失败或 G1/G2 结论。

修复后从 Luna 的项目外工作目录对三个空间各执行两轮“项目详情→页面规范→完整能力清单→精确入口→能力声明”只读交错查询，六轮均能持续读取四个入口及 enabled=true。已通知原三个 Luna 会话在项目 135/136/137 的已有页面上继续补齐动画，后续仍由用户验收。

### 海报越界与内容校验闭环

用户反馈三份产物均无动画后，将处理范围缩至一份。只修复工作空间 46 的项目 135：四个动画页的 `poster.atMs` 超过实际时长，导致初始化失败；改为视觉末尾的 `readable` 标签与 `applyPoster: true`。真实项目窗口预览保持海报，进入放映后四页均观察到随时间变化并抵达 completed，重新进入可重播；另外两个项目未修改。这是指定产物的故障复核，成品仍由用户验收。

平台侧补齐错误闭环：Runtime 登记并等待目标画布的时间轴初始化，在静态上下文准备和采样海报；内容错误通过 `render-ready.contentExceptions` 返回 Renderer。诊断返回 severity=error，截图拒绝成功产物；保留错误码、字段与轨道定位，Backend 返回失败且不可作为基础设施问题盲目重试。代码检查规则版本同步更新，避免继续命中历史误报通过缓存。CLI 全局 Skill 更新至 1.4.6，推荐末尾标签而非猜固定海报毫秒数。

本轮验证：

- Runtime 全量 166 files / 1321 passed / 3 skipped；正式类型检查、构建与相关文件 ESLint 通过。
- Renderer 全套与 render-contracts 共 78 passed；保留已有 Windows subprocess 清理提示。
- Backend 代码检查、缓存与指纹共 35 passed；能力目录与 CLI Skill 示例契约另 19 passed，Runtime 目录及内容校验最终定向 21 passed；仓库契约 63 passed。CLI Skill 管理/诊断/字体工作流共 27 passed；wheel/sdist 内容和哈希验证通过，全局 Skill 状态为 1.4.6/up_to_date。
- 复用本地服务，通过真实 CLI → Backend → Renderer → Runtime 链路只读校验页面 736 的候选：3000ms 海报、2570ms 实际时长返回 `valid=false`、`TIMELINE_SCHEMA_INVALID`、`timeline.poster.atMs` 及实际范围；合法 `readable` 标签候选返回 `valid=true`、无警告。证据位于本地 `.tmp/motion-project135/*-poster-validation.json`，候选校验未修改现有页面版本。

仅重启已确认归属的 Backend 与 Renderer 加载修复，保留本地授权试用入口，未修改 `.env` 或重置开发数据。未开展完整 E2E、G1/G2、生产裁剪镜像或长时间稳定性验收，正式默认开关仍关闭。

### 旁白页初始化与失败页导航回归

用户在工作空间 50、项目 139、页面 757 放映时遇到时间轴缺失，且无法回到上一页。真实 Chromium 复现确认：音频暂停在 0 秒、无时间轴句柄；原因是生成源码将 `voice` 的 `asset` 写成 `assetName`。已通过有版本保护的精确编辑修正，页面由 v8 升至 v9，Job `job-cada1d9727ee4e2d88a21f50cf02f536` 成功，检查无警告，路由的 timeline_end 覆盖保留。

本轮同时修复三个平台时序/恢复问题：

- 单页异步模块尚未加载时，占位画面就能被标记为 render-ready；现在等待主预览的真实加载终态，再等待时间轴初始化并收集错误，缩略图不参与该等待。主预览加载失败/超时不能返回成功；代码检查规则升至 `code-check-rules.v3-preview-mount-readiness`，使历史误报通过结果失效。
- 页面句柄先于默认海报采样完成注册，放映宿主可能提前播放并与采样争用媒体；宿主现在先等待页面初始化结束，且换页后丢弃旧初始化结果。
- 错误/受阻状态原先只允许下一页；现在双向手动翻页都经过统一清理、新 generation 和目标页准备，首末边界及原下一页循环规则保持不变。

验证证据：

- Runtime 最终全量 166 files / 1331 passed / 3 skipped；类型检查、正式构建与相关文件 ESLint 通过。新增回归覆盖真实 ViewPreview 延迟加载、错误旁白、加载失败/超时、初始化期间换页，以及失败/受阻后的上一页和旧回执隔离。
- Backend 缓存与指纹 16 passed；仓库契约 8 files / 63 passed。
- 实际 CLI → Backend → Renderer → Runtime 拒绝错误 `assetName` 候选，返回 `TIMELINE_SCHEMA_INVALID` 与 `timeline.tracks[0].asset`，合法编辑则保存 v9。
- 真实项目浏览器验证错误页上一页可用，回到故障页后下一页也可离开；修复后音频未静音、volume=1、进度大于 0.5 秒，回上一页停止，返回后从头重播，开启自动模式后在旁白与 1 秒视觉收尾结束后进入 `/review`。最终初始化/播放错误为 0。实际扬声器听感仍由用户验证，不将浏览器播放状态写成物理出声验收。
- 在补齐宿主初始化等待前，完整播放复测曾发生海报采样/播放争用并超时；修复后完整流程通过，保留失败与成功原始记录，不抹去失败试验。证据存于本地 `.tmp/motion-round2/voice-*`，不入库。

本轮只做故障修复及对应回归，未运行完整 E2E、G1/G2、双窗口、生产镜像或长期稳定性测试。只重启已确认归属的本地内测 Backend 加载校验规则，保留现有 Renderer/Runtime/Editor 与开发数据。

### 翻页入场前海报闪现回归

用户补充：直接在页面 761 进入放映正常，但从 757 翻页进入时，会先看到全部元素，再重新入场。逐帧复现确认：新页在过渡期间应用了 `applyPoster: true` 的完整海报，约 0.5 秒后放映宿主才开始播放并回到零点。这是 Runtime 的预览/放映上下文问题，无需逐页修改创作源码。

- `usePageTimeline` 改为读取最近宿主注入的执行策略；窗口预览/卡片保持交互预览作用域，全屏放映采用 presentation，静态父级策略仍不可被放宽。
- 放映挂载时立即准备原生视觉与兼容 DOM 轨道的初态，即使源码设置 `applyPoster: true` 也不采样预览海报；宿主仍等待过渡与初始化结束再开始播放。窗口预览和静态捕获继续显示可读海报，降动效保留静态可读映射。
- 快速切页卸载后不再采样已释放的 transport，迟到的初始化回执不作为当前页错误上报。

真实 Chromium 从 757 到 761 的逐帧记录中，播放前可见的完整海报由约 25 帧降为 0 帧，首帧及过渡期间标题和错峰条目均保持初态，最终播放错误为 0。直接在 761 进入放映仍从零点播放，窗口预览全部条目保持可读；旁白页有声播放状态、上一页停止、返回重播与 timeline_end 进入复习页的完整流程再次通过。证据保存在本地 `.tmp/motion-round2/flash-*` 与 `voice-flash-regression.log`。

本轮 Runtime 全量 167 files / 1338 passed / 3 skipped，类型检查、正式构建与相关文件 ESLint 通过；Backend 代码检查/缓存/指纹 35 passed，Renderer 内容错误映射 3 passed，仓库契约 8 files / 63 passed。实际 CLI → Backend → Renderer → Runtime 对 761 的新候选只读校验返回 valid=true、无错误或警告，未写入页面。未开展完整 E2E、G1/G2、生产镜像或长期稳定性验收，复用现有开发服务与数据。
