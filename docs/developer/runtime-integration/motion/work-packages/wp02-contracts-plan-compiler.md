# WP02 契约与计划编译

状态：完成（纯逻辑层）。主责：跨模块契约 / Runtime core。前置：[WP01](./wp01-baseline-engine-spike.md)。

## 输入与落点

消费[G0 决定](../g0-decision.md)与[创作方向](../authoring-contract.md)，由本包形成正式的单一字段基线。资源定义/规范计划需要 Schema、类型与共享正反例，视觉保留受控 GSAP 填充函数；不照旧 JSON 草案建立完整视觉 DSL。

## 交付

- 冻结资源定义、规范计划、受控视觉构造入口、默认值、时间边界、目标类型与窄公开句柄；类型派生或对拍，不手写多套字段事实源。
- 将标签、afterTrack、媒体/动作实际时长和重复转换为确定的绝对轨道区间与主时钟区间；为相同定义生成稳定 planDigest。
- 校验重复 id、非法数值、依赖环、属性所有权冲突、无穷完成依赖、缺失目标与 poster 越界。
- 定义与引擎无关的 prepare/applyAt/freeze/dispose 适配接口、异步取消信号和状态证明；WP04–WP06 消费该接口。
- 冻结错误码与 fieldPath/trackId 定位，接入既有检查 envelope；明确哪些可由 Schema 校验、哪些必须等 Runtime 解析后校验。
- 记录 remote render v2、slideshow schema 3 与 presenter v4 的字段迁移清单，执行实现仍由 WP08/WP09 各自维护。

## 验证与通过条件

共享用例覆盖 A01 与乱序采样；相同语义的定义归一化稳定，编译不读取 DOM、不播放媒体、不执行回调。资源时长未知时返回明确的准备依赖，不伪造 duration。

正反例应能定位到具体约束，不能只做代码字符串快照。资源定义/规范计划的 JSON 往返不丢失标签、裁切与结束姿态；原生视觉函数仍作为源码，不伪装成 JSON 可序列化对象。

## 交接

发布内部类型与适配器接口给 WP03–WP07，暂不加入面向普通模型的可执行 Runtime Kit 推荐。

## 实施记录

- 代码版本与冻结 Schema：`runtime/src/core/motion/{types,errors,compile,sampling}.ts`；page-timeline.v1 字段、错误码、适配器接口与 64 位稳定摘要已落地，公开 `.vN` 入口由 WP10 包装。
- 实际命令、通过/失败数量与 fixture 位置：`pnpm --filter web-runtime-vue exec vitest run src/core/motion`，WP02 14 项通过；正反例内联在 `compile.test.ts`，覆盖依赖环、属性冲突、主媒体约束、时长未解析、海报与标签。
- 未覆盖项：真实浏览器适配器时序由 WP04–WP06 验证；Backend 对任意 TypeScript 视觉函数不做完整解析，符合本包边界。
