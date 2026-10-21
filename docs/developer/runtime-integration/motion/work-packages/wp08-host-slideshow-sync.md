# WP08 放映宿主与双窗口

状态：待实施。主责：Runtime shell / Backend。前置：[WP04](./wp04-dom-adapter.md)、[WP05](./wp05-media-adapter.md)、[WP06](./wp06-model-adapter.md)、[WP07](./wp07-asset-capabilities.md)。

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

- 代码版本、配置和同步协议版本：待回填。
- 实际命令、结果、双窗口和旧行为回归证据：待回填。
- 未覆盖项：待回填。
