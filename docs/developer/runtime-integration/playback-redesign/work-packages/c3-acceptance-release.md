# C3 集中实机验收与交付

状态：待实施。主责：跨模块验证。前置：[C2](./c2-legacy-zero.md)。出口：GC。

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

### 待建入口（旧实现已随 C2 删除，仓库内无替代）

- **30 分钟受控长稳**：原入口 `tests/experiments/motion-g1/run.mjs --soak` 已删除。需重建有头运行、全屏透明输入 guard（以 `noExternalInput` 为通过条件）、CDP `Memory.getDOMCounters().jsEventListeners` 低水位、RAF 间隔与 dropped-frame 采集，并区分有头/无头 wake lock 结论。
- **A04 模型进出保留曲线与 WebGL 恢复**：没有存活的挂载/卸载循环脚本，`WEBGL_lose_context` 丢失与恢复演练也没有入口；先建脚本再取修复或接受结论。
- **多屏 `getScreenDetails` 授权**：缺观众窗口多屏授权的真实演练入口；当前窗口全屏回退不能记为通过。
- **Firefox/WebKit 与移动端**：仓库没有对应 project 或设备入口；未验证即在支持矩阵记为明确不作承诺。

### 版本与指标记录

每份证据固定记录：候选源码 commit、CLI 与 Skill 版本、`/api/system/slideshow-capabilities` 与 `/api/system/scene-capabilities` 摘要、`editor/src/types/openapi.json` 摘要、Runtime Kit manifest 版本与 `.runtime-build-id`、镜像标签与三角色启动结果。实机指标记录 Chromium 版本、JS 堆、DOM/节点/监听器计数、RAF 间隔与掉帧、媒体元素与 WebGL context 数、Renderer 进程与槽位状态、本地产物路径。历史 G1/G2 数值只作参考，不与本轮混记。

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
