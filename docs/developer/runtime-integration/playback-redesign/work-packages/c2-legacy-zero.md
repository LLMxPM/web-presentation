# C2 旧链路清零与文档

状态：待实施。主责：跨模块。前置：[B5](./b5-config-and-clients.md)、[C1](./c1-static-capture.md)。出口：GC。

## 交付

- 全仓检索兜底，清除 B 段未删净的旧入口：`core/motion` 剩余模块（transport、compile、sampling、native-visual 白名单、default-adapters、target-registry、media-adapter、model-adapter、preview-bridge、page-motion-contract）、`Asset*.v2`、`usePageTimeline.v1`、旧 Presenter 双向协议的消息类型（`navigate`、`playback-command`、`playback-state`、`display-status`）与命令动作、时间轴阶段枚举、旧媒体完成判定；无运行时 fallback。
- 清理牵连的测试与实验产物：`tests/e2e/specs/smoke/motion-*.spec.ts`、`tests/e2e/specs/runtime-heavy/motion-*-capture-opt-in.spec.ts`、`backend/tests/contracts/test_runtime_module_policy.py`、`test_runtime_kit_components.py` 与 `runtime-kit.manifest.json` 中的旧登记。`tests/experiments/motion-g1/` 是删除还是保留为历史证据，按验证产物入库边界写明结论。
- 更新顶层 `README.md` 与 `AGENTS.md`：AGENTS.md 中检查指纹缓存、截图/诊断身份、「`transition`/`advance`/`playback` 与 `app` 展示字段不得进入身份」、页码分配规则共用 fixtures 等约束会因推进模式重定义而变动，需同步。
- 更新用户放映/动画/音频说明、Runtime 开发文档、AI 指南、A2 产出的支持矩阵与发布检查表。
- 旧专题文档（motion、slideshow、audio、threejs）状态行改为历史实现记录并指向本方案，不再被模型当成当前创作指南；正文保留为实施历史。

## 验收

非归档源码、manifest、当前用户文档与生成物检索无旧 API/字段的有效引用；Runtime、Backend、Editor、Renderer、RenderContracts、CLI 对应测试与生成门禁通过；删除后从空开发库仍能完成新建项目到播放的流程。本包只要求自身测试与生成门禁通过，全量主门禁在 C3 收口。
