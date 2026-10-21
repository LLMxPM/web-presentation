# WP03 时钟状态与目标所有权

状态：完成（虚拟时钟与纯状态层）。主责：Runtime core。前置：[WP02](./wp02-contracts-plan-compiler.md)。

## 输入与落点

依据 [运行契约](../runtime-contract.md) 实现 core/motion 的 transport、clock、target-registry 和 seek coordinator。纯状态与 Vue 注入、DOM 调度分别放置。

## 交付

- 实现播放意图与运行阶段分离、位置、速度、完成集合和单调时钟；媒体时钟由适配器提供真实进度。
- 实现 pagePath/generation 与 seek revision 围栏，准备、暂停、定位、重播、取消和幂等 dispose。
- 为每个实际目标发放独占控制权，识别类型与注册时机；未登记媒体继续留给旧会话。
- 实现主媒体结束后的显式时钟交接，错误、buffering 或用户暂停不被误判为正常结束。
- 任意时间采样禁用事件副作用；无限装饰不参与主时长、完成或后继依赖。
- 暴露有界状态快照给 shell、预览和诊断，公共代码不取得其它页面或宿主的内部状态。

## 验证与通过条件

虚拟时钟覆盖 A02、A09、A10 的状态层：乱序回执、连续 seek、restart、主媒体边界、用户暂停与缓冲恢复。每会话最多一个主动 tick，dispose 后状态不再提交。

直接 applyAt(t) 与任意前序位置之后 applyAt(t) 的规范状态一致；没有真实目标时不通过全局选择器猜测目标。

## 交接

WP04–WP06 只需实现适配接口即可接入，不各自创建全局时钟。WP08 通过此快照与命令桥接放映，不复制状态机。

## 实施记录

- 代码版本：`runtime/src/core/motion/{transport,target-registry,adapters}.ts`；状态机区分播放意图与运行阶段，定位使用递增 revision，主媒体结束后显式交接单调时钟。
- 实际命令、结果与虚拟时钟用例：`pnpm --filter web-runtime-vue exec vitest run src/core/motion`，WP03 8 项通过；覆盖暂停不前进、缓冲不恢复用户暂停、blocked 手势重试、乱序定位与采样摘要稳定。
- 未覆盖项：真实媒体/视频帧回执与跨域 iframe 宿主由 WP05、WP08 的浏览器场景验证。
