# 首期编排创作契约方向

状态：G0 已选定 GSAP 与“受控原生视觉＋资源 builder”，详见[G0 决定](./g0-decision.md)。本文固定职责与形状，正式字段、方法名和公开 `.vN` import 由 WP02/WP10 定义，当前没有新公共能力。[此前 JSON 草案](./authoring-json-draft.md)保留为历史设计资料，不再作为唯一创作入口或直接实施的 Schema。

## 一份 SFC，两类定义

- 资源依赖采用有类型的有限 builder，编译为可校验计划。资源/片段引用来自真实查询，时长来自准备结果；不把 URL、猜测的动作名称或私有对象写进计划。
- 视觉采用 GSAP 原生填充函数，支持局部作用域、标签、错峰和函数/段落复用。Runtime 已创建暂停时间轴，作者只追加效果，不另建播放时钟或资源调度。
- 两类定义都保存在现有 Vue SFC 版本中，不增加第二份 Editor 时间轴数据或数据库表。规范化资源计划可序列化，视觉函数仍是源码；Backend 不通过正则假装完整解析任意 JavaScript。
- 不把所有视觉属性、缓动和复用重新包装成完整 JSON DSL。机器 Schema 应覆盖真实可校验资源与规范计划，视觉语法/属性边界由 WP02 明确。

研究形状示意，不能作为当前平台调用：

```ts
const story = useGsapStory(stage, props, ctx => {
  const plan = ctx.resources()
    .voice('voice')
    .clip('model', queriedClipRef, { atMs: detailStartMs })
    .video('demo', { inMs: 1000, outMs: 3000 }, { after: 'model', offsetMs: 200 })
    .build()
  return {
    plan,
    visual(timeline) {
      timeline.fromTo('.title', { opacity: 0, y: 32 },
        { opacity: 1, y: 0, duration: seconds(400) }, 0)
      // 资源 id 自动登记成标签，可以使用 'model'、'demo' 作为插入点。
    },
  }
})
```

## Runtime 拥有的边界

| 内容 | 创作代码 | Runtime |
| :--- | :--- | :--- |
| 资源 | 查询后使用摘要/句柄，声明片段和裁切 | 鉴权、metadata/动作摘要、准备与版本核对 |
| 视觉 | 原生效果、标签/位置、错峰和复用 | 作用域、暂停时间轴、显式初态、静默采样、固化与撤销 |
| 时钟 | 使用资源标签和统一转换 helper | 唯一播放所有者、媒体时钟/交接、定位修订号、策略 |
| 三维 | 片段引用、实例目标和支持的整体变换语义 | 私有 Mixer、克隆实例、动作采样、姿态和释放 |
| 媒体 | 有限裁切、required/optional等正式声明 | play、pause、seeked/视频帧、blocked/buffering与静音 |

创作上下文只包含本实例目标、只读资源摘要与受控句柄，不传内部模型 sample/dispose、Object3D/Mixer 或原始媒体控制器。窄类型不是 JavaScript 安全沙箱；真实所有权与权限仍由 Runtime/Backend 的执行边界保证。

资源、transport、捕获统一毫秒；GSAP 原生参数保持秒，通过单一 helper 转换。资源 id 自动登记视觉标签，减少重复计算。作者不能在 `.call()` 中补造音视频播放、网络操作或业务状态。静态/乱序定位不得补发回调。

## WP02 必须正式化的契约

1. 稳定轨道 id、标签、绝对起点、命名后继、并行及缺失/循环依赖；资源句柄与目标命名空间。
2. 片段 index/语义签名/版本，真实时长、裁切、速率、有限重复、结束姿态、主媒体限制及完成判定。G0 夹具签名只是动画 JSON 摘要，不能充当正式动作语义算法。
3. 视觉显式初态与同目标/属性的所有权、支持属性、有限段落复用及非法语法处理。本轮验证 opacity/y 与显式 fromTo，不能把全库插件、任意回调或重叠覆盖自动视为已支持。
4. 函数构造异常、首次准备、取消与旧回执，统一生命周期和错误语义。研究 helper 不能代替生产 transport 的完整状态协议。
5. 后端源码边界校验、受信 Runtime/Renderer 执行回执与规范计划 Schema；不得在 Backend 内运行浏览器或执行任意 Vue。
6. 有界 code/fieldPath/trackId，Schema 单一源、生成类型与正反例；公开入口遵守 Runtime Kit `.vN` 和 manifest 规则，v1 既有内容不被改写。

正式契约继续遵守[运行与捕获契约](./runtime-contract.md)中的唯一所有者、策略独立、身份与发布围栏。产品规模和性能预算留后续复核，不从第一轮历史数字默认为已冻结。
