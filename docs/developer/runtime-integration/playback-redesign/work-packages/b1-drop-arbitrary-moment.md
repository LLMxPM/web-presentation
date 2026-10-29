# B1 删除指定时刻截图协议

状态：完成（2026-10-29，开发验证通过；实机验收移交 C3）。主责：Runtime / Backend / Renderer / render-contracts。前置：[B0](./b0-static-presentation.md)。出口：GB 的协议清理。

本包先删除未正式开放的指定时刻截图协议。B0 已使默认截图和导出不再依赖时间轴 poster 采样；正向播放仍使用旧编译器与 Transport，其移除必须与 B2 的新播放会话同批完成，不能在替代执行器落地前删掉正在使用的 `applyAt`。

## 交付

- 删除截图入口的指定时刻 `sampleAt`、时间轴标签/偏移选择器和页面捕获桥；清理静态帧身份中只服务动作取帧的 `motionKey`。`usePageTimeline.v1` 仍被旧播放和 Editor 预览使用，其公开 `seek/sampleAt`、内部编译计划、适配器 `applyAt` 与采样调度暂不拆除；由 B2 新播放器和 B5 新预览调用端接管后删除，不能在 B1 提前破坏现有放映。
- 契约侧删除：`packages/render-contracts/src/render_contracts/motion.py:16-42` 的 `motion_snapshot`（`timeline_id`/`at_ms`/`at_label`/`offset_ms`/`visual_mode`）与 `schemas/execution-request.v2.json` 对应字段；Python DTO 与 JSON Schema 双份事实源同步修改并对拍。
- Backend 侧删除：`schemas/timeline.py` 的 `TIMELINE_CAPTURE_SNAPSHOT_ENABLED` 与 `ExternalTimelineCapabilities` 中的 capture 披露、`services/page_screenshot_job_service.py:147` 分支、`models/page_screenshot_job.py:47-48` 的 `motion_snapshot_json`/`_hash`、`schemas/page.py:225` 与 `external_api.py:291` 的对应字段。
- Renderer 侧同步删除 `motion_snapshot` 消费点与 `tests/test_motion_capture.py` 中依赖取帧的用例；默认 PNG 与诊断附图继续走 B0 的静态态。
- **保留**：B2 切换前仍驱动放映的旧内部计划与适配器；资源读取、首帧就绪探针、静态帧采集、截图身份及所有发布围栏。
- 更新 OpenAPI 与生成的 Editor API 类型，执行生成契约门禁。

## 开发验收

契约正反例与对拍测试、Renderer 单测及默认 PNG、附图、静态导出的无浏览器集成用例通过；API 与生成物无 `motion_snapshot` 有效字段，显式旧选择器明确拒绝。保持默认路径接线，真实 PNG 与导出产物在 C3 验证。旧内部编译器与 `applyAt` 暂留并记录调用点，由 B2 清零；不得为满足检索门槛删掉现有播放路径。

## 实施记录

基于 B0 `4d05161` 完成外部截图协议删除，详见[开发记录](../development-record.md#b1-删除指定时刻截图协议2026-10-29)。默认 PNG、附图和导出继续使用独立静态态。旧选择器在内部/External API、控制协议 v1/v2、Python DTO 和离屏导出均被明确拒绝，生成 DTO 已同步。

新增删列迁移 `20261029_0100`：终止遗留的活跃选择器任务，保留 SQL NULL/JSON null 的默认任务、PNG 引用及发布围栏，恢复五字段静态去重。未运行开发库迁移。删除永久放弃的 opt-in 取帧 E2E，A15 改为静态就绪观察；旧播放浏览器夹具由 C2 继续适配，C3 正式执行。

开发验证：Runtime 全量 1367 通过、3 跳过，check/build 通过；Renderer 53、RenderContracts 40、Backend 截图链 74 项通过；迁移行为 4 通过、1 跳过（未配置 PostgreSQL）；Editor check、API 生成和生成漂移检查通过。夹具 TypeScript/Vue/MJS 语法通过。未运行真实浏览器、远程截图、导出产物和生产镜像。
