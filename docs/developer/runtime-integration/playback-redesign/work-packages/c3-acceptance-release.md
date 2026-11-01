# C3 集中实机验收与交付

状态：已通过（2026-11-01，GC 判定通过）。本轮范围：motion 相关实机项与全量主门禁；`compose-images`、Renderer 取消/超时/迟到 PNG 专项、独立 ZIP 三项与本次 motion 改动无关，按既有验收沿用、本轮未重跑。主责：跨模块验证。前置：[C2](./c2-legacy-zero.md)。出口：GC。

本包统一执行原 A1/A2 及 B0–C2 移交的实机任务，只验证最终收敛实现。A/B/C1/C2 的开发测试不能代替本包证据；本包通过前不宣称新模型已交付或 G2 已关闭。

C1 已于 2026-10-31 完成工程收口（`5bd6d3f`，见 [C1 接线与验证](./c1-static-capture.md)）。静态捕获策略为 `page-static-capture.v3`；本包须对最终候选实测共享视频探针、模型静态帧失败整体中断、组件静态诊断与场景回执、关闭完成前不披露产物、取消/图片超时后的迟到 PNG 拒绝发布。开发替身的临时目录/槽位断言不能作为真实 Chromium 进程已释放的证据。

## C2 整理的执行入口（2026-10-31）

入口按 C2 清零后的实际仓库状态整理。服务探测与复用顺序、E2E 数据纪律、全量门禁与专项矩阵见 [dev-start-test](../../../../../.agents/skills/dev-start-test/SKILL.md) 与[测试矩阵](../../../../../.agents/skills/dev-start-test/references/testing-matrix.md)。C2 只准备入口，未执行任何一项实机验收。

### 已有入口

| 验收范围 | 入口 | 素材与场景 |
| :--- | :--- | :--- |
| 放映推进与静态产物 | `pnpm run test:e2e:prepare` 后 `pnpm exec playwright test --config tests/config/playwright.config.ts --project=smoke tests/e2e/specs/smoke/scene-playback.spec.ts` | `tests/e2e/helpers/scene-page-source.ts` 的 blocking 标题＋数字滚动页与 ambient 无限装饰页；`manual/timer/scene_end` 三种推进、完成后停留、ambient 不阻塞、保持/释放、`scene_end` 缺 blocking 任务报错、媒体目标缺失有界错误、指定状态截图字段 422、独立构建后播放并导出 PDF、PPTX/PDF 前后静态一致、远程 PNG 可读默认态 |
| 双窗口与 v5 协议 | 同上，`scene-presenter.spec.ts` | BroadcastChannel `web-presentation:presenter:v5:*` 探针；protocol 3/4 与旧 `navigate` 伪造包必须被丢弃，只有观众窗口推进 Scene |
| Editor 预览与资源替换 | 同上，`scene-editor-preview.spec.ts`、`scene-resource-replacement.spec.ts` | 页面详情预览播放/停止；合法替换图片后刷新资源身份与预览像素 |
| 三维替换后片段失效 | 同上，`scene-model-replacement.spec.ts` | `tests/e2e/helpers/skinned-glb.ts` 的 `buildSkinnedGlb`（真实 joint 驱动、BoneSlide 片段，签名从 `analysis_metadata` 读取） |
| 受保护媒体 | 同上，`protected-media.spec.ts` | 受保护视频与音频的 HEAD、Range 与视频跳转定位 |
| 静态跨产物与发声隔离 | 同上，`scene-export-isolation.spec.ts` | `tests/e2e/helpers/media-wav.ts` 的 `toneWavBuffer(30)` 真实旁白＋10 秒位移序列；静态姿态、放映姿态与结束姿态互不重合，远程 PNG → 预览默认态 → 放映发声 → 退出 → PPTX/PDF 全链路 |
| 联合创作闭环 | `SCENE_JOINT_ACCEPTANCE_ENABLED=true pnpm exec playwright test --config tests/config/playwright.config.ts --project=runtime-heavy scene-joint.spec.ts`（有头实例） | 蒙皮 GLB＋旁白 WAV＋cue WAV；模型动作 → 旁白 `afterTrack` → ambient cue，`audio_settings.cue_bindings` 使用 `transition.forward` 与 `interaction.joint-finished`；同时核对 `/api/system/slideshow-capabilities`（schema 4）与 `/api/system/scene-capabilities` |
| 三维真实像素与真实构建 | `--project=runtime-heavy model3d-screenshot.spec.ts`、`project-build.spec.ts` | `media-fixtures.ts` 的 `buildRedModelGlb`；沙箱项目真实构建成功 |
| Renderer 与契约 | `pnpm run test:renderer`、`pnpm run test:render-contracts`；真实链路由上述远程 PNG、诊断附图与取消用例覆盖 | 取消后 attempt 终态、迟到 PNG 拒绝发布需在真实 Renderer 取证，后端单测不能替代 |
| 镜像与三角色 | `python scripts/contracts/check-image-startup.py --image <tag> --variant runtime\|renderer\|lite\|full`、`python scripts/contracts/renderer-image-probe.py`、`pnpm run test:contracts:compose-images`、`python scripts/testing/docker-architecture.py`；分角色模板为 `deploy/compose/compose.runtime-roles.yml` | `docker_architecture_env.py` 真实编排 `preview`/`build`/`check` 三副本；核对 `__runtime_healthz`、`__runtime_readyz`、`runtime_kit_version` 与 `.runtime-build-id` |
| 全量主门禁 | `pnpm run test:all` | 收口阶段执行；失败回修到责任包后重跑受影响项 |

### 已补建的观测入口（2026-10-31）

C2 清零时缺失的四类入口已在 `tests/e2e/specs/acceptance/` 补建，作为独立 `acceptance` project 运行；该 project 不在 `test:e2e:all` 与 `test:all` 内，只能显式指定。所有证据同时写入测试附件与 `.tmp/c3-evidence/*.json`。

| 验收范围 | 入口 | 观测与通过条件 |
| :--- | :--- | :--- |
| 30 分钟受控长稳 | `pnpm run test:c3:soak`（自带 `--headed --workers=1`，默认 30 分钟；`C3_SKIP_SOAK=1` 跳过，自检可 `C3_SOAK_MINUTES=1 C3_SOAK_ALLOW_SHORT=1`） | 15 秒采样 JS 堆、DOM/节点/`jsEventListeners` 低水位、RAF 间隔与掉帧、媒体/WebGL 计数、Renderer 槽位与进程数；通过条件为全程 `noExternalInput`、无错误覆盖层、保留上下文不超过 B3 有界池上限、槽位回到 idle |
| A04 保留曲线 | `pnpm run test:c3:a04`（默认 100 轮，`C3_A04_CYCLES` 仅供脚本自检下调） | 每轮进出模型页并在 GC 后采样堆、监听器、上下文创建/丢失/存活、浏览器渲染进程；曲线与 `controlBarHitTest` 一并入证据，结论由 C3 判定修复或接受 |
| WebGL 丢失/恢复 | 同上入口的第二条用例 | `WEBGL_lose_context` 丢失后让出一次宏任务再请求恢复；断言恢复成功或页面给出明确错误，静默失效不算通过 |
| 多屏授权 | `pnpm run test:c3:multiscreen`（有头、单 worker） | 在顶层观众窗口经 CDP 授予 `windowManagement` 后调用 `getScreenDetails()`，记录屏幕数量与 `verdict`；无头实例一律 `NotAllowedError`，编辑器预览 iframe 受 Permissions Policy 限制，两者都不作为结论；单屏环境记为不可验证，不以当前窗口全屏回退冒充通过 |
| 受保护媒体慢速传输 | `... --project=acceptance protected-media-slow.spec.ts` | 挂起受保护媒体请求复现 `waiting`，断言成立后才放行，要求真实恢复播放且页面内容区只有一个视频元素 |

脚本自检（1 分钟长稳、3 轮进出，只证明入口可执行，不作为验收证据）：长稳 4 个样本，`noExternalInput=true`、槽位 `idle`、RAF P95 13.5ms、掉帧 4、媒体 1、保留上下文 1；A04 堆 33.3→34.9 MiB、监听器 116→146、上下文创建 1 存活 1；WebGL `lost=true/restored=true`；多屏在有头实例取到 `screens=1`、判定单屏不可验证；慢速媒体 `waiting=1`、恢复 `playing=1`。

待 C3 判定、本次不预设结论的观测项：全幅页面内容会盖住控制条命中区域（`elementFromPoint` 落在页面内容上，演练用事件派发绕过）；有头运行时 `data-wake-lock` 记录为 `denied`。

Firefox、WebKit 与移动端仍不建入口：仓库没有对应 project 或设备入口，本机虽已安装 Firefox/WebKit 浏览器二进制，但缺少设备与移动端拓扑，按「未验证、不作支持承诺」回填支持矩阵，改动前不得记为通过。

### 版本与指标记录

每份证据固定记录：候选源码 commit、CLI 与 Skill 版本、`/api/system/slideshow-capabilities` 与 `/api/system/scene-capabilities` 摘要、`editor/src/types/openapi.json` 摘要、Runtime Kit manifest 版本与 `.runtime-build-id`、镜像标签与三角色启动结果。实机指标记录 Chromium 版本、JS 堆、DOM/节点/监听器计数、RAF 间隔与掉帧、媒体元素与 WebGL context 数、Renderer 进程与槽位状态、本地产物路径。历史 G1/G2 数值只作参考，不与本轮混记。

## 执行记录（2026-10-31 至 11-01）

候选提交 `b0300b3`（产品代码同 `db68ff2`，`0cf71ae`/`b0300b3` 只改 C3 入口与镜像探针）。环境为 Windows 11 + 本地 `_e2e` 服务（`AI_TEST_MODE=mock`）与开发栈（真实模型）两套，未改动 `.env` 与开发库既有数据。

| 验收项 | 命令 | 结果 |
| :--- | :--- | :--- |
| smoke 全套 | `--project=smoke` 单 worker 跑 scene-* 与 protected-media | **21/21 通过**；2 worker 并行时「无限 ambient 装饰不阻塞 scene_end 推进」因 CPU 抢占动画变慢超时，单跑 13/13，非回归 |
| 联合闭环 | `SCENE_JOINT_ACCEPTANCE_ENABLED=true --project=runtime-heavy scene-joint.spec.ts --headed` | 通过（34.8s），三维动作、旁白、切页 cue 同一放映协作，静态截图不被媒体阻塞 |
| 三维像素与真实构建 | `--project=runtime-heavy model3d-screenshot.spec.ts project-build.spec.ts` | 3/3 通过（普通模型、蒙皮模型、沙箱项目真实构建） |
| A04 保留曲线 | `C3_A04_CYCLES=100 --project=acceptance model-a04.spec.ts` | 通过：堆 75.6→78.4 MiB（10/25/50/75/100 轮为 77.5/77.7/78.0/78.3/78.4，趋于平坦）、监听器 116→136 稳定、上下文创建 1 存活 1、残留画布 0 |
| WebGL 丢失恢复 | 同上第二条用例 | `lost=true`、`restored=true`、恢复后上下文可用 |
| 30 分钟长稳 | `pnpm run test:c3:soak`（有头） | 通过：119 个采样、`noExternalInput=true`、槽位全程 idle、RAF P95 13.4ms、媒体元素 1、Renderer 服务进程 2、保留上下文 1、无错误覆盖层。**堆指标不采用**：当时 CDP 口径跨 iframe 抖动，已改为运行时帧内 `performance.memory`，未重跑 |
| 多屏授权 | `pnpm run test:c3:multiscreen`（有头） | 有头取到 `screens=1`，判定 `single-display-not-verifiable`；无头实例一律 `NotAllowedError`，编辑器预览 iframe 受 Permissions Policy 限制 |
| 受保护媒体慢速传输 | `--project=acceptance protected-media-slow.spec.ts` | 通过：挂起请求后 `waiting=1`，放行后 `playing=1`，页面内容区视频元素 1 |
| 镜像构建 | `docker build -f runtime/Dockerfile`、`renderer/Dockerfile`、`deploy/docker/Dockerfile.platform`、`Dockerfile.lite` | 四类镜像均构建成功（tag `c3-0cf71ae`，runtime 2.29GB / renderer 1.6GB / platform 659MB / lite 2.77GB）。Docker Hub 持续 EOF，改用本地缓存基础镜像离线构建；platform/lite 的 `# syntax=docker/dockerfile:1.7` 前端镜像不可拉取，用去掉该 parser 指令的本地副本构建（两文件无 heredoc/mount/network 语法，指令等价） |
| 镜像启动校验 | `check-image-startup.py --variant runtime/renderer/lite/full` | 四类全部通过：runtime `runtime_version_guard_passed`、renderer `renderer_control_api_capture_passed`、lite `runtime_version_and_renderer_capture_passed`、full 健康通过 |
| 三角色编排 | `docker-architecture.py setup --backend-image wp-platform:c3-0cf71ae --runtime-image wp-runtime:c3-0cf71ae --renderer-image wp-renderer:c3-0cf71ae` | preview_a/b、build_a/b、check 全部 `healthy`；`healthz` role 正确、`readyz` 全 ok、build 的 `buildWorker.ready=true`；五个实例 `build_id` 均为 `sha256-fb1a46b4fe10…`，`runtime_kit_version=1.0.0`；演练环境已 `cleanup` |
| 真实模型创作 | 受控工作空间 + `agent-coordinator` 真实 Run（非 mock） | Run `24c1cab3…` 完成（68s），页面 783 生成 v2 并插入日期行；回读源码确认；默认截图任务 708 `succeeded`，PNG 17019 字节，sha256 与 `result_screenshot_id` 一致 |
| 全量主门禁 | `CODEBUDDY_SAFE_DELETE_ENABLED=0 pnpm run test:all` | **通过**（exit 0）：Backend 全量、Editor gate 905 项、Runtime gate、根仓 contracts、render-contracts、Renderer 68 项、python-workspace 17 项、E2E 40 通过 + 1 条按设计跳过（联合闭环需显式开关）。前两次失败分别为 pytest 临时目录清理被本机删除保护拦截、以及编辑端路由守卫用例 5 秒超时（单跑 1.7s，负载抖动），均已分别以 basetemp/环境开关与显式用例超时修正 |
| CLI 读写 | `wp --json -w 61 project get` → `wp project update --payload-file` → 回读 | CLI 0.4.1 通过 PAT（workspace:read / project:read,write / page:read,write）连本地 Backend，描述由空回写为「C3 CLI 回写 2026-11-01」并回读一致 |

证据目录：`.tmp/c3-evidence/`（`a04-100cycles-*.json`、`soak-30m-*.json`、`webgl-restore-*.json`、`three-role-image.json`、`real-creation-*.json`、`cli-readwrite.json`、`image-startup-*`）；Playwright 产物在 `test-results/`，镜像启动证据在各 `image-startup-*` 子目录。

**本轮未重跑、按既有验收沿用**：`test:contracts:compose-images`（本轮实跑仍在传输层 `error pinging v2 registry: EOF`，4 个镜像均无法核对）、Renderer 取消/超时/迟到 PNG 专项、独立 ZIP 产物核对。这三项与本次 motion 改动无交集，收口判定为沿用；未做 `reused_evidence` 的三镜像/页面版本/ZIP 摘要身份匹配，若后续改动触及 Renderer 取消、镜像发布或 ZIP 导出，需单独重验。

**仍不覆盖**：Firefox/WebKit 与移动端（无 project 与设备拓扑）、操作系统真实睡眠与恢复、无人值守长期放映——不作支持承诺。长稳堆指标因口径修正未重跑，若需引用堆趋势，请以 A04 的 100 轮曲线为准，或按新口径重跑一次长稳。

## 交付

- 固定候选源码版本、CLI/Skill 版本、OpenAPI 摘要、Runtime Kit 与 Runtime 构建身份；按 dev-start-test 探测和准备隔离验证环境。自动化 E2E 只使用独立 `_e2e` 数据，不重置开发库；内置助手真实创作另用受控工作空间，mock 结果不能当成真实模型创作通过。
- 在同一受控工作空间与 A2/B5 准备的样例上，分别经 Editor、内置助手、CLI 完成读取能力 → 创建/修改 → 等待 Mutation Job → 回读最终版本 → 默认截图与候选诊断附图。验证能力隐藏、失败语义、权限与工作空间隔离，不泄露存储键或票据（承接原 A1/G2-01）。不要求指定时刻截图，也不恢复 B01–B08 量化门槛。
- 真实 Chromium 贯通正式预览与全屏放映：多条 DOM 序列、数字滚动、打字机、SVG 描边、DOM/CSS/Canvas 粒子、两个模型动作、旁白、静音视频、无限装饰和 cue；验证播放、退出、翻页、`manual/timer/scene_end`、有限任务完成与 `ambient` 不阻塞。
- 验证观众窗口唯一调度与演讲者窗口有限意图/原子状态：重复/旧 revision 丢弃、重开对齐、`hold/release`、退出全屏、BroadcastChannel 不可用时 localStorage 降级、后台节流与隐藏/恢复、冻结后不连跳。只验 B5 最终协议，不补跑旧 Presenter v4（承接原 A2/G2-08）。
- 用真实受保护端点与受控慢速传输复现 `waiting` 与恢复；验证媒体受阻、观众窗口本地手势重试、单一自动发声主媒体、旁白与 cue 真实发声、演讲者窗口不自动播媒体、离页后不重试旧任务（承接原 A1/A2、audio WP06/WP12/WP20、G2-11）。
- 真实 WebGL 验证双模型首帧和动作隔离、资源替换后片段失效、快速切页与重进、`WEBGL_lose_context` 丢失/恢复或明确错误、实例释放互不污染（承接原 A2/G2-07）。
- 在同一含模型与动画的页面上取得远程 PNG、写入附图、缩略图、PDF/PPTX，验证可读静态内容一致、不发声、不执行受托管回调、不推进 Mixer；覆盖默认态、显式海报态、非受托管动画页面、`unsupported`、资源失败与任务跳过。独立截图的 `STATIC_PRESENTATION_UNAVAILABLE` 不可重试，附图不可用不覆盖诊断成功，缩略图有原因占位，导出整体失败并指出页码（承接 B0/C1）。
- 发起长截图任务后取消，记录 attempt 终态、临时文件、Chromium 存活/僵尸进程、槽位回 idle、取消后新任务可执行以及迟到结果不提升产物（承接原 A1/G2-09）；后端单测通过不能代替真实 Renderer 清理证据。
- 从最终候选源码重建生产依赖裁剪镜像，preview/check/build 三角色真实启动；核对 `__runtime_healthz`、`__runtime_readyz`、`__runtime_version`、构建身份与 Runtime Kit 一致，不以开发依赖补齐（承接原 A1/G2-02）。构建 ZIP 解压后以 `index.html` 为入口，脱离开发服务器验证全屏、双窗口、三种推进模式、旁白/cue 与静态导出。
- 回填支持矩阵：浏览器、窗口拓扑、屏幕数量、部署形态、各放映入口逐项给出通过、失败或未验证；观众窗口多屏授权、Firefox/WebKit、移动端未验证的明确不作支持承诺。使用当前窗口全屏回退不能记为多屏授权通过（承接原 A2）。
- 至少 30 分钟受控循环，记录 JS 堆、RAF/计时器、媒体元素、WebGL context、canvas、Renderer 进程/槽位，并补 G2-04 要求的 dropped-frame 与 RAF 间隔指标。沿用既有 soak 证据方法：有头运行加全屏透明输入 guard 并以 `noExternalInput` 为通过条件；CDP `Memory.getDOMCounters().jsEventListeners` 用低水位而非首尾中位数；wake lock 结论区分有头与无头（无头返回 `NotAllowedError`）；合成 `freeze` ＋ `pageshow(persisted=true)` 不等于真实操作系统睡眠，须注明未验证。时长若短于旧证据的 61 分钟需说明理由。
- 按 B3 的 renderer 所有权决策给出 A04/G2-06 的修复或接受结论：修复需复测 100 次进出后堆稳定；接受则记录增长曲线、影响边界（文档销毁后释放）与后续计划，不宣称零增长。
- 收口全量主门禁与相关专项门禁，修复中间态积累的红项；必需场景不能以“已记录问题”替代通过。可排除的环境边界须明确不支持及理由，不把核心链路失败改成不支持规避验收；据此判定 motion G2 是否可正式关闭。
- 汇总能力、限制、实际命令、通过/失败数量、支持矩阵与发布检查表；只有证据齐全才把新模型标为已交付，旧 G2/M2/M3 结果不能代替本次验收。产出实测缺口清单，区分能力、环境、指引和待验证问题，给出 D1 是否启动的结论及依据。

## 执行顺序与失败回修

1. 先确认候选版本、素材、执行环境和 A2/C2 用例入口，运行全量主门禁及相关专项；按技能顺序准备和复用服务，不与其它整套测试并行。
2. 执行正式服务链路、联合创作、静态跨产物、Renderer 取消、多窗口与媒体/WebGL 异常场景，回填支持矩阵。
3. 从通过开发与链路验证的候选源码构建最终镜像，验证三角色及独立构建产物。
4. 对最终候选执行受控长稳与 A04 资源曲线观测，汇总证据、缺口与交付结论。

“集中”是把实机安排在实现之后，不要求失败后整轮从头重跑。失败回修到责任包，重跑相关开发测试与受影响实机场景；修改执行代码、依赖或构建输入后重新生成并确认镜像/产物身份，长稳覆盖最终候选。每份证据记录版本、命令、结果与本地产物路径；历史或旧候选证据只作参考。

## 验收

本包必需验收与全量门禁须在合并 main 前完成；开发分支可提前公开新能力用于调试，不能将“已开放开发入口”视为本包验收通过。

上述必需场景、全量主门禁与相关专项门禁通过，支持矩阵与发布检查表回填完成。记录实际命令、结果、版本、失败重跑和未覆盖项；没有实测的环境不宣称支持。不得用单测、开发替身或开发服务器截图替代真实 Renderer、生产产物、多窗口与长稳证据。
