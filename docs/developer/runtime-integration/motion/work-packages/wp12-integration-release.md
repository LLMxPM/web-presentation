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
