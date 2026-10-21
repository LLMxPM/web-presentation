# WP09 捕获协议与静态导出

状态：待实施。主责：render-contracts / Renderer / Backend / Runtime。前置：[WP04](./wp04-dom-adapter.md)、[WP05](./wp05-media-adapter.md)、[WP06](./wp06-model-adapter.md)、[WP07](./wp07-asset-capabilities.md)。

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

- 代码版本、协议和身份规则版本：待回填。
- 实际命令、结果、产物位置与清理证据：待回填。
- 未覆盖项：待回填。
