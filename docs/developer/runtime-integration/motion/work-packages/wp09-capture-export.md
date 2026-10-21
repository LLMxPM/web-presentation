# WP09 捕获协议与静态导出

状态：待验收（协议、Renderer 与 Runtime 捕获桥已实施；真实链路取帧证据待补）。主责：render-contracts / Renderer / Backend / Runtime。前置：[WP04](./wp04-dom-adapter.md)、[WP05](./wp05-media-adapter.md)、[WP06](./wp06-model-adapter.md)、[WP07](./wp07-asset-capabilities.md)。

## 输入与落点

复用 render_requests、远程 Worker、render-ready、OffscreenPageStage、模型静态帧与 validation_screenshot_publisher；捕获选择器与身份只以 [运行契约](../runtime-contract.md) 为准。

## 交付

- 为 internal/render/v2、render-ready.v2 增加 motionSnapshot 和目标状态回执；Python DTO 与 JSON Schema 对拍，v1 老请求继续可用。
- Backend 按 Worker 能力与 Runtime 发布身份派发，新字段不发给旧 Worker；无匹配执行者明确失败。
- 实现无声音、无事件副作用的 sample → 媒体定位/模型绘制 → 样式固化 → 状态证明 → 捕获。
- 对 PNG、PDF、PPTX 使用同一默认 poster 或指定选择器；不承诺把动画或音视频嵌入静态文件。
- 贯通截图/检查/模型帧缓存身份，防止不同时间共用旧帧。临时截图不覆盖默认指针，源码/资产变化后按既有围栏复核发布。
- 取消、超时、旧 attempt、WebGL 或视频帧失败释放浏览器/槽位/临时产物；附图失败不覆盖已完成的诊断。

## 验证与通过条件

覆盖 A13–A15：同一时刻重复与乱序 sample、动画禁用兜底不改帧、视频裁切中间帧、模型姿态、海报与临时截图隔离。

真实完整链路包含 Backend → Renderer → 独立 Runtime → 可读 PNG、PDF/PPTX 目检与取消清理。运行 render-contracts 双向对拍、Renderer、Backend 协调器和静态导出回归。

## 交接

向 WP10/WP11 提供稳定的捕获选择器与错误结构；为 WP12 提供 G1 取帧、v1/v2 和默认发布证据。

## 实施记录

- 代码版本、协议和身份规则版本：
  - 控制协议 `internal/render/v2`、Runtime 就绪协议 `render-ready.v2`、Runtime 捕获桥 `motion-snapshot.v1`；v1 路径与旧请求继续可用。
  - `ExecutionRequest.motion_snapshot` 支持 `at_ms` 与 `at_label + offset_ms` 互斥选择，`visual_mode` 为 `full|reduced`；`ExecutionResult.applied_motion` 回执有界，显式选择器要求 `status=applied` 且 timeline/采样时间一致。
  - Renderer 能力同时公布 `supported_protocol_versions` 与 `supported_runtime_protocol_versions`；Backend 仅在页面捕获/诊断且 Worker 支持 v2 时派发 v2，显式选择器遇到 v1 Worker 或 Runtime 不声明 v2 均以契约不匹配失败，不静默降级。
  - 预览地址附加 `runtimeCaptureProtocol=2`，Runtime 按该标记初始化 v2 桥；Renderer 在静态准备与视觉资源就绪之后采样时间轴并截图，导出路径在同一采样后再准备静态模型帧。
  - 支持 v2 的 Worker 执行默认截图时同样通过 poster 采样；旧 Worker 或旧 Runtime 保留原有静态行为。PNG/PDF/PPTX 未指定选择器时使用页面 poster，旧页面无时间轴桥时保留静态默认，显式指定时间轴则失败。
- 实际命令、结果、产物位置与清理证据：
  - `uv run pytest packages/render-contracts/tests -q` → 30 passed。
  - `uv run pytest renderer/tests/test_motion_capture.py renderer/tests/test_static_capture.py -q` → 12 passed；`uv run pytest renderer/tests -q --ignore=renderer/tests/test_startup_check.py` → 41 passed。
  - `uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_render_motion_dispatch.py backend/tests/unit/test_render_control_plane.py backend/tests/unit/test_render_lifecycle.py backend/tests/unit/test_render_static_navigation.py backend/tests/unit/test_render_attempt_late_failure.py backend/tests/unit/test_render_result_conflict.py -q` → 58 passed。
  - `pnpm --filter web-runtime-vue exec vitest run src/core/motion/capture-bridge.test.ts src/core/utils/render-ready.test.ts src/core/services/export/OffscreenPageStage.test.ts` → 14 passed；Runtime `vue-tsc --noEmit` 通过。
- 未覆盖项：
  - 尚未运行 Backend → Renderer → 独立 Runtime 的真实 PNG/PDF/PPTX 取帧与目检，视频中间帧、模型姿态、同刻重复/乱序、取消与临时产物清理只有单元/契约证据。
  - 外部异步截图任务与临时选择器持久化归 WP11；当前默认截图任务不接收选择器，因此不存在临时帧覆盖默认指针的路径，但也没有真实任务侧身份对拍。
