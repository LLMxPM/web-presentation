# C2 旧链路清零与文档

状态：**完成（2026-10-31，工程与文档收口；实机待 C3）**。主责：跨模块。前置：[B5](./b5-config-and-clients.md)、[C1](./c1-static-capture.md)。出口：GC 的工程前置；GC 尚未通过。基线提交：`b9d4d6d`；本包改动记录时仍在工作树，未提交、未推送。

## 交付

- 全仓检索兜底，清除 B 段未删净的旧入口：`core/motion` 剩余模块（transport、compile、sampling、native-visual 白名单、default-adapters、target-registry、media-adapter、model-adapter、preview-bridge、page-motion-contract）、`Asset*.v2`、`usePageTimeline.v1`、旧 Presenter 双向协议的消息类型（`navigate`、`playback-command`、`playback-state`、`display-status`）与命令动作、时间轴阶段枚举、旧媒体完成判定；无运行时 fallback。
- 清理牵连的测试与实验产物：`tests/e2e/specs/smoke/motion-*.spec.ts`、`tests/e2e/specs/runtime-heavy/motion-*-capture-opt-in.spec.ts`、`backend/tests/contracts/test_runtime_module_policy.py`、`test_runtime_kit_components.py` 与 `runtime-kit.manifest.json` 中的旧登记。`tests/experiments/motion-g1/` 是删除还是保留为历史证据，按验证产物入库边界写明结论。
- 更新顶层 `README.md` 与 `AGENTS.md`：AGENTS.md 中检查指纹缓存、截图/诊断身份、「`transition`/`advance`/`playback` 与 `app` 展示字段不得进入身份」、页码分配规则共用 fixtures 等约束会因推进模式重定义而变动，需同步。
- 更新用户放映/动画/音频说明、Runtime 开发文档、AI 指南、A2 产出的支持矩阵草稿与发布检查表。支持状态区分待验证与明确不支持，C3 实测后回填最终结论；不得提前写为已支持。
- 整理 C3 的真实浏览器、Renderer、镜像三角色、独立产物与长稳执行入口；确认素材、场景、版本和指标记录齐全，删除依赖旧时间轴的过期断言。只准备入口，不在本包提前跑一轮正式实机验收。
- 旧专题文档（motion、slideshow、audio、threejs）状态行改为历史实现记录并指向本方案，不再被模型当成当前创作指南；正文保留为实施历史。

## 开发验收

旧入口、旧 manifest 与有效调用点清零是合并 main 前必须通过的门禁；开发分支可先公开和调试新 Scene，不能据此提前隐藏新入口或阻塞开发。

非归档源码、manifest、当前用户文档与生成物检索无旧 API/字段的有效引用；Runtime、Backend、Editor、Renderer、RenderContracts、CLI 对应开发测试、文档链接与生成门禁通过，C3 执行入口可追溯到用例与证据清单。从隔离测试库新建项目到实际播放、全部实机与全量主门禁统一在 C3 收口；本包不启动完整实机环境，也不重置开发库。

## 完成记录（2026-10-31）

基线 `b9d4d6d`。全程未启动或重启平台服务、未准备 E2E 环境、未重置开发库、未修改 `.env`；未提交、未推送。

### 1. 旧入口删除

删除 28 个 Runtime 源文件与测试文件：`runtime/src/core/motion/` 整目录（adapters、compile、default-adapters、dom-adapter、errors、index、media-adapter、model-adapter、native-visual、page-motion-contract、readiness、resource-builder、sampling、target-registry、transport、types 及 7 个测试）、`runtime-kit/public/composables/motion/usePageTimeline.v1.ts` 与 3 个测试、`runtime-kit/internal/renderers/model3d/motion/motion-contract.ts`（保留同目录 `animation-signatures.ts` 与 `sha256-bytes.ts`，仍服务 `AssetModel.v3` 片段签名）。

交付清单中列出的 `preview-bridge` 不在 `core/motion`：B2 已把它建在 `runtime/src/core/scene/preview-bridge.ts`，属现行 Scene 预览桥，保留。`Asset*.v2`、`useAudioCue.v1`、`PageMediaSession` 与旧媒体完成判定已由 B3/B4 删除，本包复核无残留。

调用端同步清理，不留 fallback：

- `core/utils/render-ready.ts` 删除 motion readiness 等待，静态就绪只由 `settleStaticPresentation` 决定，失败回执并入 `contentExceptions`。
- `core/scene/dev-debug.ts` 删除旧句柄冲突探测（`SCENE_DEBUG_LEGACY_CONFLICT`）。
- `core/execution/execution-policy.ts` 删除 `allowAutoStart` 标志与 `shouldStartAutomatically`/`shouldAdvanceAutomatically`（已无生产调用方）；保留 `mediaPlaybackMode` 与 `allowAutoAdvance`。
- `runtime-kit.manifest.json` 删除 `usePageTimeline.v1` 整条导出，`usePageScene.v1` 约束改为「同一页只使用 Scene 一种编排」。

旧 Presenter 双向协议在 B5 已收敛为 v5 单向广播，线上消息类型不含 `navigate`/`playback-command`/`playback-state`/`display-status`。本包清理残留命名：`presenter-sync-protocol.ts` 的意图动作统一为 `PresenterSyncIntentAction`，`PresenterDisplayView.test.ts` 的 v4 mock 签名改为 v5。`presenter-playback-state` 与 `presenter-console__display-status` 是 DOM testid 与样式类名，不是协议消息类型，保留。

### 2. 测试与实验产物

E2E 按「主体存续则移植、主体删除则删断言」处理，不新写实机验收：`motion-*.spec.ts` 七个 smoke 与 `runtime-heavy/pre-motion-joint.spec.ts` 改名为 `scene-*.spec.ts` / `scene-joint.spec.ts` 并迁到 `usePageScene.v1` + `useStaticPresentation.v1` + schema 4 + Presenter v5；`motion-protected-media.spec.ts` 改名 `protected-media.spec.ts`。新增 `tests/e2e/helpers/scene-page-source.ts`（blocking 标题＋数字滚动、ambient 无限装饰、旁白三个构造器），`motion-media.ts` 改名 `media-wav.ts` 并只保留真实 WAV 构造，`motion-skinned-model.ts` 改名 `skinned-glb.ts`。删除 `tests/e2e/helpers/motion-page-source.ts`。

Backend 契约测试改为断言旧入口不存在：`test_runtime_module_policy.py` 与 `test_runtime_kit_components.py` 增加 `usePageTimeline.v1 not in`，并断言 `usePageScene.v1`/`createSceneMediaTask.v1`/`useAudioCue.v2`/`AssetModel.v3` 不可预览且有 usage。`test_render_motion_dispatch.py` 改名 `test_render_static_dispatch.py`；`test_code_check.py` 的内容错误样例由 `TIMELINE_SCHEMA_INVALID` + `timeline.poster.atMs` 改为 `MODEL_CLIP_STALE` + `scene.tracks.model`；`test_project_slideshow_settings.py` 合并两条仍用 `media_end`/`timeline_end` 命名的重复用例为 `test_project_create_should_accept_scene_end_advance`。Renderer 侧 `test_motion_readiness.py`/`test_motion_capture.py` 已改名并改写为内容错误诊断与就绪协议用例。

Editor `ProjectPresentationConfigDialog.test.ts` 的能力 mock 从 schema 2（`media_end`、`media_timeout_ms`、`page_narration: false`）改为 schema 4 单一工厂函数；`tests/contracts/runtime-backend/route-page-number-projection.test.ts` 的投影无关字段改用 `scene_end`/`completionDelayMs`；`backend/app/schemas/audio.py` 旁白禁循环注释改指 `scene_end`。

**实验产物结论**（按验证产物入库边界）：

| 目录 | 结论 | 依据 |
| :--- | :--- | :--- |
| `tests/experiments/motion-g1/` | **删除** | 10 个文件直接 import 已删除的 `core/motion`、`usePageTimeline.v1` 与旧媒体会话，无法在现行仓库执行；其 A01–A16 结论已固化在 `docs/developer/runtime-integration/motion/g1-automation-coverage.md`，原始 JSON 与截图按边界只留本地 `.tmp/motion-g1/`，不入库。 |
| `tests/experiments/motion-regression/` | **删除** | 同上，4 个文件依赖旧隔离 Chromium 采样链。 |
| `tests/experiments/motion-g2/` | **删除** | 仅 `prepare-assets.mjs` 一个文件，import 已删除的 `motion-g1/fixtures.mjs`，成为悬空孤儿；G2 素材由 C3 按新入口重新准备。 |
| `motion-authoring`、`motion-wp01`、`motion-story`、`motion-luna`、`motion-final` | **保留为历史证据** | 五个目录相互引用但对平台源码零 import（已按 `runtime/src`、`backend/app`、`@runtime-kit`、`tests/e2e/helpers` 检索确认），是 GSAP/WAAPI/Anime 选型与创作形状的自包含评估夹具；其中的 `TIMELINE_*`、`MODEL_ANIMATION_REFERENCE_STALE` 是本地定义的模拟常量，不构成对平台旧 API 的有效引用。保留 G0 决策依据，不再执行，也不作为新实现的验收证据。 |

### 3. 检索清零

对 `*.{ts,vue,py,json,js,mjs,yaml,yml}` 与 `*.md` 全仓检索 `usePageTimeline`、`core/motion`、`page-motion-contract`、`target-registry`、`native-visual`、`default-adapters`、`PageMediaSession`、`Asset{Audio,Video,Model}.v2`、`useAudioCue.v1`、`motion_snapshot`、`TIMELINE_*`、`MODEL_ANIMATION_REFERENCE_STALE`、`posterTimeMs`、`sampleAt`、`auto_start`、`media_end`、`timeline_end`、`media_timeout_ms`、`timeline_timeout_ms`、`playback-command`、`页内时间轴`。剩余命中全部属于下列四类，无一处是有效调用：

1. **拒绝封装**：`render_contracts/schema.py` 与两版 `execution-request.v*.json` 的 `not: required`、`services/rendering/coordinator.py` 的旧字段守卫、`slideshow-config`/`page-transition`/`playback-controller` 的旧配置明确失败用例、`scene-playback` 与 `scene-export-isolation` 的 422 用例、`usePresenterController.test.ts` 注入 v4 包证明被丢弃。
2. **负向断言**：`test_runtime_module_policy.py`、`test_runtime_kit_components.py`、`runtime-kit.manifest.test.ts`、`test_system_slideshow_capabilities.py`、`test_unified_tool_specs.py`、`test_static_screenshot_migration.py`、`project-slideshow-values.test.ts`。
3. **迁移与历史命令记录**：`backend/migrations/versions/2026102*_*.py`、`20261030_0100_scene_slideshow_default.py` 的 `_V3` 旧默认值，以及 `docs/developer/runtime-integration/motion/` 内已加历史横幅的实施记录。
4. **收敛方案自身**：`playback-redesign-proposal.md`、A1/B0–B5/C1 各卡与 `development-record.md` 中描述「删什么」的条目；`development-record.md` 里指向已删除源文件的两个链接改为行内代码并标注「已于 C2 删除」，文档链接门禁恢复 0 断链。

`tests/fixtures/slideshow-contract-cases.json` 的 `legacy-*` 与 `old-mode`/`removed-budget` 用例均为 `valid: false` 拒绝样例，保留。

### 4. 文档更新

- 顶层 `README.md` 与 `README.zh-CN.md`：核心能力条目去掉「（开发分支）」限定，改为 Scene 是唯一页内编排入口、旧链路已整链删除、完整实机验收待 C3；中文 README 原「页内时间轴放映」条目整体替换。
- `AGENTS.md`：新增「页内编排与放映约束」四条（Scene 唯一入口与已删除清单、GSAP 只经受管门面、schema 4 三种翻页模式与 Backend/Editor 同批修改、自动媒体显式接管与静态上下文不发声）。检查指纹缓存、截图/诊断身份、「`transition`/`advance`/`playback` 与 `app` 展示字段不得进入身份」与页码 fixtures 共用约束复核后**未改动**：该段已按新模型表述（「播放进度、运行期回调实例与 Scene/Deck 状态不进入身份」「静态出口不得通过推进 Scene、媒体或 Mixer 取帧」），推进模式重定义不影响其结论。`tests/fixtures/route-page-number-cases.json` 的 `playback_fields_never_reach_the_projection` 用例与 `tests/contracts/runtime-backend/route-page-number-projection.test.ts` 同批把 `media_end`/`mediaTimeoutMs` 换成 `scene_end`/`completionDelayMs`，保持两侧对拍一致。
- 用户文档：`docs/user/workflows/slideshow.md` 按 schema 4 与「全屏即放映」重写，新增「支持状态」小节区分目标支持待实机验收 / 明确未验证不作承诺 / 明确不支持（暂停、定位、指定状态截图、任意时刻状态重建、混版运行——永久移除，不以兼容开关恢复）；`preview-build-export.md` 翻页方式同步。
- Runtime 与集成文档：`static-presentation.md`、`scene-development.md`、`page-animation-guide.md`、`runtime/README.md`、`slideshow/README.md`、`audio/README.md`、`audio/contract.md`（版本条目补充「已删除的 v2 不复用」）、`testing/README.md`、`projects/audio/acceptance.md`。`slideshow/contract.md` 复核后确认 B5 已写为 schema 4，未改动。
- AI 指南：`backend/app/ai/animation_authoring_standard.py` 删除旧时间轴表述，`tool_specs.py` 同步 schema 4。
- 支持矩阵草稿 `a2-support-matrix.md` 与 `docs/deployment/release-checklist.md` §5/§7 改为待 C3 回填，未提前写为已支持。
- 旧专题文档：`docs/developer/runtime-integration/motion/` 下 25 个 `.md`（含 `work-packages/`）加「历史实现记录」横幅并指向收敛规划与现行入口，`runtime-contract.md` 与 `authoring-contract.md` 状态行改为历史实现记录；`README.md` 原已有横幅，未改。`docs/developer/projects/threejs-resource-implementation-plan.md` 复核后确认横幅已在位。slideshow 与 audio 专题是当前契约而非历史记录，按现行 schema 4 更新而不加历史横幅。

### 5. C3 执行入口

已在 [C3](./c3-acceptance-release.md) 新增「C2 整理的执行入口」：已有入口逐条映射到 spec 文件、素材构造器与镜像/部署脚本；同时明确四类**待建入口**（30 分钟长稳、A04 进出保留曲线与 `WEBGL_lose_context`、多屏 `getScreenDetails` 授权、Firefox/WebKit 与移动端），因为旧长稳与保留曲线脚本随 `motion-g1` 删除后仓库内没有替代实现。版本与指标记录项已列明。本包未执行任何一项实机验收。

### 实际验证

| 命令 | 结果 |
| :--- | :--- |
| `pnpm --filter web-runtime-vue test --maxWorkers=4` | 178 文件，1400 通过、3 项既有跳过（`runtime/src` 下 177 个测试文件 + `runtime/vite.config.test.ts`）；本包删除 10 个旧 motion/usePageTimeline 测试文件 |
| `pnpm --filter web-runtime-vue check`、`build` | 均通过；构建 5522 模块 |
| `pnpm --filter editor test`、`check`、`build` | 160 文件 / 904 通过；类型检查与生产构建通过 |
| `uv run --no-sync --project backend pytest -c backend/pyproject.toml backend/tests/contracts -q` | 76 通过、7 跳过；跳过全部是 `test_runtime_state_adapter.py` 未配置 `RUNTIME_STATE_PARITY_REDIS_URL` 的既有环境跳过 |
| Backend 定向（`api/test_project_slideshow_settings.py`、`api/test_system_slideshow_capabilities.py`、`unit/test_render_static_dispatch.py`、`contracts/test_runtime_module_policy.py`、`contracts/test_runtime_kit_components.py`） | 29 通过 |
| Backend 定向（`contracts/test_code_check.py`） | 19 通过 |
| Backend 定向（`integration/ai/test_ai_generic_business_tools.py`） | 11 通过 |
| Backend 定向（`contracts/test_cli_skill_examples.py`） | 4 通过 |
| Backend 定向（`unit/test_unified_tool_specs.py`、`unit/test_ai_agent_catalog.py`、`contracts/test_runtime_kit_components.py`） | 12 通过；`tool_specs.py` 与 `animation_authoring_standard.py` 的 schema 4 表述无目录漂移 |
| `pnpm run test:renderer` | 68 通过 |
| `pnpm run test:render-contracts` | 58 通过 |
| `pnpm run test:contracts` | 20 文件，129 通过；含 E2E 收集数量契约 |
| `pnpm run test:contracts:generated` | 通过；269 paths / 367 schemas，生成物与 Backend 完全一致 |
| `pnpm run test:repository` | 8 文件，63 通过；文档链接 0 断链 |
| `npx playwright test --config tests/config/playwright.config.ts --list` | 40 个用例 / 21 个文件，改名与删除后收集完整 |
| 相邻 CLI 仓 `uv run --no-sync pytest packages/api-client/tests packages/cli/tests -q`（`d8a4d27`，工作树干净） | 212 通过；跨仓 `test_backend_openapi_contract.py` 单独复跑 1 通过，**未 skip**，即按当前主仓 OpenAPI 实际对拍 |

### 未运行项与后续边界

- 未运行任何浏览器、远程 Renderer、镜像、独立构建产物、多窗口或长稳验证；未运行 `pnpm run test:all` 全量主门禁。E2E 只验证到 `--list` 收集，用例本身需要 C3 在独立 `_e2e` 环境执行。
- 未运行 Backend `api`/`integration`/`unit` 全量，只运行与本包改动相关的定向集合；全量归 C3 收口。
- CLI 与 Skill 版本仍是 B5 交付的 0.4.1 / 1.4.7，本包未改 External API 契约（生成物零漂移可证），因此未发布新版本。
- MCP 不在交付链，未触碰。
- 合并 `main` 的门禁含义不变：本包证明旧入口、旧 manifest 登记与有效调用点已清零，但**不代表 GC 通过**；GC 需要 C3 的实机、镜像、支持矩阵与长稳证据。
