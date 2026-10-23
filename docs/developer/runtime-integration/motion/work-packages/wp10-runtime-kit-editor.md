# WP10 公共入口与预览控制

状态：完成（2026-10-23 首期收口；A12 Editor 预览控件证据见 [G1 映射](../g1-automation-coverage.md)；生产镜像最终重建与 v1 回归转 G2）。主责：Runtime Kit / Editor。前置：[WP08](./wp08-host-slideshow-sync.md)、[WP09](./wp09-capture-export.md)。

## 输入与落点

以 WP02 定义的内部接口封装 usePageTimeline.v1 与 AssetAudio/AssetVideo/AssetModel.v2，复用内部执行器。Editor UI 实施前完整阅读根 DESIGN。

## 交付

- 发布一个模型常用入口：definition 与 bindings 分开、类型限制目标 key 和轨道，少量预设共享同一计划编译器。
- 更新 Runtime Kit manifest、usage、constraints、参数 Schema 与返回示例；v1 行为保留，不让旧源码获得隐式自动播放。
- 内部样例可独立预览组件轨道片段，但实际页面仍只有一个 transport；销毁预览作用域释放目标。
- Editor 增加显式播放、暂停、重播、定位、状态与偏好模拟；默认 poster，调试偏好只影响当前预览，不改变操作系统设置。
- 增加 timeline_end 项目/路由表单与继承说明、动作摘要展示和定位错误；不提供首期图形轨道编辑器。
- 模型写入与可视化样式编辑继续以源码为权威；预览控制不写回另一套时间轴数据。

## 验证与通过条件

覆盖 A03、A12、A15 和 B01–B05 的使用体验。类型错误在准确的字段出现，运行错误映射到具体轨道；不能要求模型手写事件监听、缓冲处理或 RAF。

Editor 组件/布局验证、Runtime Kit manifest 跨端校验、旧 v1 页面回归，以及生产裁剪后的入口加载均通过。

## 交接

向 WP11 提供可执行示例、真实 import path、能力隐藏规则与标准错误示例；G2 前保持普通用户的能力关闭。

## 实施记录

- 代码版本、manifest 与公开入口：
  - 新增 `usePageTimeline.v1`：接收静态 definition 与 bindings，DOM 轨道 target 由类型限制为绑定 key；元素绑定写入实例级临时属性并在释放时清理，字符串绑定直接作为局部选择器。
  - 公开接口返回只读 plan/state/error 与 prepare/play/pause/resume/restart/seek/sampleAt/setMuted/setVisualMode/dispose；交互式预览自动应用 poster，捕获/导出与放映由各自宿主驱动。
  - 新增 `AssetVideo.v2`、`AssetAudio.v2`、`AssetModel.v2`：复用 v1 解析与渲染器，固定隐藏控件、禁止 autoplay/原生循环、关闭模型交互，并使用 `data-runtime-kit-motion="timeline"` 标记受控目标。
  - manifest 增加四项真实版本化路径，均标记 `enabled=false`、`previewable=false`、`internal-only`，G2 前不进入普通模型能力目录；v1 路径与行为保持不变。
  - transport 增加 `visualMode` 只读属性与 `setVisualMode`，准备后按当前位置重新应用；该模式不进入计划摘要与截图身份。
  - Runtime 新增 `runtime-preview-motion.v1` 预览桥：只接受父窗口同源消息，支持 sync/play/pause/restart/seek/set-visual-mode，250ms 广播有界状态，无时间轴时返回空状态。
  - Editor `RuntimePreviewFrame` 校验来源窗口与 origin 后接收状态；页面预览新增播放/暂停、重播、拖动定位、降动效模拟和错误提示，不写回项目配置。
  - 项目与逐路由表单补充 timeline_end 等待上限、无时间轴兜底和继承摘要；资产详情补充动作时长、签名与不支持原因。
- 实际命令、结果、预览截图和旧页面证据：
  - `pnpm --filter web-runtime-vue exec vitest run src/runtime-kit/public/composables/motion/usePageTimeline.v1.test.ts src/runtime-kit/public/components/assets/assets-v2.test.ts src/core/motion/preview-bridge.test.ts src/core/motion/transport.test.ts src/runtime-kit/manifest/runtime-kit.manifest.test.ts` → 34 passed。
  - `uv run --project backend pytest -c backend/pyproject.toml backend/tests/contracts/test_runtime_module_policy.py backend/tests/contracts/test_runtime_kit_components.py -q` → 15 passed。
  - `pnpm --filter editor exec vitest run src/components/runtime-preview/RuntimePreviewFrame.test.ts src/components/page-detail/PageDetailPreviewPanel.motion.test.ts src/components/project/ProjectSlideshowFields.test.ts src/components/project/ProjectRouteSlideshowForm.test.ts src/views/assets/model3d-summary.test.ts` → 18 passed；Editor 全量 `pnpm --filter editor exec vitest run` → 160 files / 907 passed。
  - Runtime 全量 `pnpm --filter web-runtime-vue exec vitest run` → 162 files / 1300 passed / 3 skipped。
  - Runtime `vue-tsc --noEmit` 与 Editor `vue-tsc -b` 通过。
- 首期收口（2026-10-23）：
  - 真实 E2E 已走通 Editor 预览播放、暂停、重播、拖动定位与 system/reduced/full 切换，含错误提示与海报；A12 证据见 [G1 映射](../g1-automation-coverage.md)。
  - 公开入口与 manifest 已随 2026-10-22 能力开放同步；生产裁剪 Runtime 的最终重建与独立构建加载转 [G2-02](../g2-followups.md)，v1 页面完整回归转 [G2-03](../g2-followups.md)。
  - 组件独立轨道片段预览仍无真实样例页面，当前只由单测覆盖，转 [G2-10](../g2-followups.md)（不阻塞 G2，支持矩阵需注明）。
