# WP08 放映宿主与双窗口

状态：待验收（代码与自动化完成；真实跨域双窗口证据待补）。主责：Runtime shell / Backend。前置：[WP04](./wp04-dom-adapter.md)、[WP05](./wp05-media-adapter.md)、[WP06](./wp06-model-adapter.md)、[WP07](./wp07-asset-capabilities.md)。

## 输入与落点

按 [运行契约](../runtime-contract.md) 修改 usePlaybackHost、PlaybackController、ExecutionPolicy、PageMediaSession 桥接、slideshow DTO/解析器和 presenter-sync-protocol。新增模块拆出目标协调与状态投影。

## 交付

- 页面资源和过渡就绪后开始；暂停、恢复、后台、离页、退出全屏与取消统一到当前 generation。
- 已注册媒体只由 transport 控制；未注册媒体保留旧用途、手动播放和恢复规则。
- 新增 timeline_end 与独立超时预算，放映 capability schema 3；manual/timer/media_end 既有语义保持不变。
- 联动项目默认值、逐路由覆盖、configuration、模板包、artifact 与构建快照，旧对象缺字段时采用规范默认，不能默默转换推进方式。
- 演讲协议升至 v4，命令去重、owner 围栏、planDigest 与 seek revision 同步；只有观众窗口运行时钟和媒体。
- 新旧会话、迟到错误和重复完成都按当前围栏处理；设置不满足时准确显示 blocked/buffering/error，不自动连跳。

## 验证与通过条件

覆盖 A02、A10–A12、A16。纯状态测试之外，以真实跨域 iframe 与双窗口验证缓冲、隐藏、退出、重连和定位。

回归已有放映快捷键、三种旧推进模式、静音和自动/手动切换；新模式无合法时间轴时明确失败。运行 DTO codegen 与共享配置往返。

## 交接

为 WP10 提供稳定控件状态/命令接口；为 WP12 提供 G1 宿主证据。此包合入不开放新模式。

## 实施记录

- 代码版本：`PlaybackController` 增加 `timeline_end`、独立 `timelineTimeoutMs`、缓冲冻结与完成/超时/缺失分支；`usePlaybackHost` 在资源就绪后准备并启动页面时间轴，向媒体会话提供独占目标过滤，并转发完成、受阻、错误与缓冲状态。`PlaybackController` 快照新增 `waitingForTimeline`；`PresenterSyncProtocol` 升至 v4，播放快照携带 `timelineId`、`planDigest`、`positionMs`、`waitingForTimeline`、`timelineIntent`、`timelinePhase`，新增 `seek` 命令与 `seekRevision` 围栏。
- 配置与能力：Backend 放映 Schema 升为 3，新增 `timeline_end`、`timeline_timeout_ms`（默认 300000，范围 1000–3600000）；`SLIDESHOW_EXECUTABLE_ADVANCE_MODES` 在 G2 前仍不含 `timeline_end`，写入由解析器明确拒绝。默认 payload、共享正反例、Runtime camelCase 映射、能力 `timeline_timeout_ms` 范围、Editor 生成类型与表单保留字段已联动。
- 自动化命令：`pnpm --filter web-runtime-vue exec vitest run src/core/motion src/runtime-shell/playback src/runtime-shell/presenter src/core/utils/page-transition.test.ts` 全部通过（含时间轴完成/超时/缺失/暂停恢复/单页循环/缓冲预算、协议 v4 定位与时间轴快照）；`pnpm exec vue-tsc --noEmit -p tsconfig.json`、`pnpm --filter editor check` 通过；Backend `test_slideshow_schema.py`、放映 API、External API、模板包与能力测试通过。
- 未覆盖项：真实跨域 iframe、双窗口 BroadcastChannel/localStorage 降级、后台节流与退出全屏的真实浏览器证据尚未执行，因此保持待验收；`timeline_end` 能力与写入仍关闭。
