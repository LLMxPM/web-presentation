# C1 静态捕获契约与回归收口

状态：**完成（2026-10-31，工程与开发回归；实机待 C3）**。主责：Runtime / Renderer / render-contracts。前置：[B3](./b3-model-forward-playback.md)、[B4](./b4-audio-ownership.md)、[B5](./b5-config-and-clients.md)。出口：GC 的工程前置；GC 已于 2026-11-01 通过。实现提交：`5bd6d3f`。

静态态、默认截图替代与不可呈现语义已在 B0 落地。本包在三维、音频、配置和客户端替换完毕后收口跨端契约与开发回归，防止 B 段重新引入播放态取帧或各出口语义漂移；真实产物一致性统一在 C3 验证。

## 交付

- 静态执行上下文继续只渲染可读默认态或显式海报态与模型静态姿态：不创建 PageScene、不运行受托管回调、不发声、不自动翻页、不推进 Mixer；页面自有代码须走 B0 的静态分支。
- 复核 B0 已冻结的呈现语义：独立截图不可呈现时返回不可重试的 `STATIC_PRESENTATION_UNAVAILABLE`；缩略图显示有原因的占位；PDF/PPTX 默认整体失败并指出页码。任务过期/未请求/预算不足的 `skipped` 不用于表达页面内容不可呈现；不得静默缺页。
- Renderer 等待字体、图片、视频 poster/首帧、模型首帧与页面静态就绪后捕获 PNG；`unsupported`、资源失败和任务跳过三类原因可追踪且不互相伪装。
- 静态截图身份只收会改变静态像素的输入：模型资源、相机与海报变化使缓存失效；播放进度、回调与过渡配置不进入身份。核对并同步 `AGENTS.md` 中检查指纹与截图身份的既有约束描述。
- 组件预览宿主页沿用同一静态语义（首轮工作空间组件不纳入 Scene）。
- 本包独占 B 段完成后的截图与 Renderer 最终契约收口，B5 不修改截图 DTO；若发现 B0 语义漂移，修正实现和跨端契约而非引入时间轴取帧兜底。

## 开发验收

跨端正反例、契约对拍、Renderer 单测与无浏览器集成测试通过；覆盖默认态、海报态、不可呈现、资源失败、身份变化、默认指针、诊断成功而附图不可用、取消与迟到产物围栏。逐项核对 PNG、附图、缩略图、PDF/PPTX 的静态上下文和就绪接线，不能留已知分歧给实机碰运气。

将同一含模型和动画页面的可读 PNG、各产物内容一致性、静态零播放、不可呈现占位/整体失败，以及真实 Renderer 取消后的进程、临时文件与槽位释放移交 C3；本包不以开发替身证明真实图像可读或浏览器已释放。

## 实现与接线核对

稳定说明回填到[独立静态呈现](../../../runtime/static-presentation.md)。本包修正了以下实际分歧：

- Runtime 资源探针新增共享静态视频准备：海报必须加载并解码；无海报才加载首帧，始终不调用 `play()` 或修改 `currentTime`。超时与取消释放图片/媒体监听和计时器。PNG、离屏导出与缩略图共用这条路径，Renderer 删除重复的首帧脚本。
- Renderer 按目标层校验单层画布与路由，资源准备完成后捕获，不再用固定 150ms 延时表达就绪。截图失败/不支持/预算不足分别保留 `failed/unavailable/skipped`；布局成功不会被图片错误覆盖。
- 正式 PDF/PPTX 单页和多页导出全部经过离屏静态舞台；缺少路由直接报错，删除主窗口 DOM 回退。模型 PNG 读回失败整体中断，清理已准备的覆盖图并保留页码/原因，不能继续输出空白模型。
- 缩略图对静态声明和资源失败显示有原因的占位。组件宿主保留执行上下文；远程组件诊断同样由 Backend 固定 `capture`，每次场景切换重新等待静态资源并返回对应 settled 回执。Editor 组件交互预览继续使用手势策略，不将工作空间组件纳入 Scene。
- `AssetVideo.posterName` / `poster-name` 与 previewSchema 海报进入资源闭包；字面量、可枚举 v-for 和动态标记沿用既有解析规则。测试验证模型文件、相机、海报声明及海报文件替换使身份变化；放映配置与非路由读取页面的目录变化仍不影响静态身份。
- 捕获策略为 `page-static-capture.v3`，由 render-contracts 常量统一驱动 Backend 指纹/请求和 Renderer 能力，避免复用修正前的图片。CLI/Skill 版本保持 `0.4.1` / `1.4.7`，未修改外部 HTTP DTO。
- 图片返回后复核取消、期限和阶段所有权；图片阶段超时后的迟到 PNG 不落盘。部分浏览器启动失败也进入关闭流程。槽位在关闭完成前只披露 `cleaning`，不提前返回成功描述符或下载产物；终态发布前再次检查取消，成功产物保留至消费，失败/取消释放临时目录和槽位。

| 出口 | 静态上下文与就绪接线 | 失败语义与开发证据 |
| :--- | :--- | :--- |
| 独立 PNG | Backend capture 导航 → render-ready → 共享资源探针 → 单层画布 → PNG | 不可呈现不可重试；任务失败不提升默认指针，保留旧版本图片为过期状态 |
| 诊断附图 | 同 attempt 先诊断再捕获，不重开浏览器 | 成功布局保留；内容 unavailable、资源 failed、预算 skipped 分开；迟到图片不注册 |
| 缩略图 | thumbnail 注入 → 静态声明 → 共享资源探针 | 内容不可呈现及资源失败显示原因占位；卸载撤销等待 |
| PDF/PPTX | capture 离屏舞台 → 静态回执 → 共享资源探针 → 模型静态 PNG 覆盖 | 缺路由、不支持、资源或模型静态帧失败整体中断，不静默缺页 |
| 组件诊断 | capture 导航 → 组件宿主 → 场景就绪/静态探针/settled | 交互上下文拒绝进入远程组件诊断；保留原场景协议，不新增 Scene |

## 实际验证

所有验证使用单测、隔离数据库和无浏览器集成；未启动/重启开发服务，未修改 `.env` 或开发数据。

| 命令 | 结果 |
| :--- | :--- |
| `pnpm run test:runtime`（本进程 `RUNTIME_ROLE=preview`） | 187 文件，1477 通过、3 项既有跳过；后续导出入口与场景回执修正按下列专项复验 |
| `pnpm --dir runtime test src/core/services/PDFExportService.test.ts src/core/services/PPTXExportService.test.ts src/core/services/pptx src/core/services/export src/core/utils/renderer-static-capture.test.ts` | 32 文件，354 通过 |
| `pnpm --dir runtime test src/views/component-preview src/core/utils/render-ready.test.ts` | 3 文件，11 通过 |
| `pnpm --dir runtime test src/core/utils/renderer-static-capture.test.ts src/core/services/export/OffscreenPageStage.test.ts src/runtime-shell/preview/ViewPreview.test.ts src/runtime-kit/public/composables/static/useStaticPresentation.v1.test.ts` | 4 文件，38 通过；含直接执行 Renderer JS 的跨端接线与共享静态样本 |
| `pnpm --dir runtime check`、`pnpm --dir runtime build` | 均通过；最终构建包含全部 Runtime 修正 |
| `pnpm run test:renderer` | 68 通过，含关闭前不发布、取消、迟到 PNG、成功保留/消费清理 |
| `pnpm run test:render-contracts` | 58 通过；共享正反例同时对拍 Python DTO 和两版 JSON Schema |
| Backend 下列 16 个文件（`uv run --no-sync --project backend pytest -c backend/pyproject.toml <文件> -q`） | 119 通过，命令文件列表如下 |
| `pnpm run test:contracts` | 20 文件，129 通过 |
| `pnpm run test:contracts:generated` | 通过；269 paths / 367 schemas，无 HTTP 生成物漂移 |
| `pnpm run test:repository`、`git diff --check` | 仓库门禁 8 文件、63 通过；diff 检查通过 |

Backend 实际文件集合（每项均以 `backend/tests/` 为前缀）：

```text
unit/test_static_presentation_screenshot.py
unit/test_mutation_screenshot_dto.py
unit/test_page_screenshot_fingerprint_service.py
unit/test_page_render_identity.py
unit/test_page_screenshot_job_service.py
unit/test_browser_capture_service.py
unit/test_resource_reference_parser.py
unit/test_code_check_fingerprint_builder.py
unit/test_validation_screenshot_cache.py
unit/test_render_static_navigation.py
integration/test_validation_screenshot_publisher.py
integration/test_page_screenshot_job_durability.py
integration/test_model3d_resource_replacement.py
contracts/test_code_check.py
api/test_page_screenshot.py
api/test_external_screenshot_jobs.py
```

本地日志在 `.tmp/c1-*.log`，不入库。初次定向测试遇到测试运行角色裁掉 Vue 插件、测试 mock 缺默认配置、测试文件 URL 被 Vite 作为资源改写及组件操作常量漏导入，均已修正并通过相关复验，不留已知失败项。

## 后续边界

- C2 可以开始：本包没有新增 Runtime Kit 入口或旧采样依赖；旧 `core/motion` / `usePageTimeline` 的删除及剩余文档清零仍归 C2。
- C3 尚未运行：最终候选的真实 Chromium/远程 Renderer、同页 PNG/附图/缩略图/PDF/PPTX 可读像素一致性、静态零发声/零 Mixer 推进、失败占位/整体导出失败、真实取消后的进程/临时文件/槽位释放，以及全量主门禁。测试替身只证明调用和围栏行为。
- Editor 全套、CLI 分发与 MCP 本次未重跑：未修改它们的实现或外部 DTO；MCP 继续不在交付链。未推送或发布。
