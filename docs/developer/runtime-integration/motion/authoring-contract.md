# 首期编排创作契约方向

状态：G0 已选定 GSAP 与“受控原生视觉＋资源 builder”，详见[G0 决定](./g0-decision.md)。2026-10-21 评审修复已将该形状接入 `usePageTimeline.v1`；2026-10-22 起公开入口默认开放，G1 已于 2026-10-23 关闭，G2 未关闭。[此前 JSON 草案](./authoring-json-draft.md)不作为默认创作入口；内部旧 `definition` 仅为既有夹具兼容。

## 一份 SFC，两类定义

- 资源依赖采用有类型的有限 builder，编译为可校验计划。资源/片段引用来自真实查询，时长来自准备结果；不把 URL、猜测的动作名称或私有对象写进计划。
- 视觉采用 GSAP 原生填充函数，支持局部作用域、标签、错峰和函数/段落复用。Runtime 已创建暂停时间轴，作者只追加效果，不另建播放时钟或资源调度。
- 两类定义都保存在现有 Vue SFC 版本中，不增加第二份 Editor 时间轴数据或数据库表。规范化资源计划可序列化，视觉函数仍是源码；Backend 不通过正则假装完整解析任意 JavaScript。
- 不把所有视觉属性、缓动和复用重新包装成完整 JSON DSL。机器 Schema 应覆盖真实可校验资源与规范计划，视觉语法/属性边界由 WP02 明确。

内部受控样例写法（能力开放前不能向普通模型推荐）：

```ts
import { usePageTimeline, seconds } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'

const story = usePageTimeline({
  root: pageRoot,
  bindings: {},
  applyPoster: true,
  timelineId: 'product-story',
  poster: { atLabel: 'readable' },
  define(ctx) {
    return {
      plan: ctx.resources()
        .voice('voice', { asset: 'voice', outMs: queriedVoiceDurationMs })
        .clip('model', queriedClipRef, { asset: 'product', startMs: detailStartMs })
        .video('demo', { asset: 'demo', inMs: 1000, outMs: 3000, afterTrack: 'model', offsetMs: 200 })
        .build(),
      visual(timeline) {
        timeline.fromTo('.title', { opacity: 0, y: 32 },
          { opacity: 1, y: 0, duration: seconds(400) }, 0)
        timeline.fromTo('.card', { opacity: 0 },
          { opacity: 1, duration: seconds(300), stagger: seconds(100) }, 'demo')
        timeline.addLabel('readable')
      },
    }
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

## 当前内部实现边界

- `define` 在页面挂载时执行一次，返回资源计划与视觉填充函数；纯视觉可使用空资源 builder。`voice/audio/video/clip` 的裁切、速率、有限重复和依赖继续复用同一规范计划编译器。
- 原生视觉支持 GSAP 3 的显式 `fromTo`、`addLabel`、原生位置字符串、非负数值 `stagger` 与填充函数复用。`from/to` 必须提供相同属性，当前支持 opacity/x/y/scale/rotation；duration 与 stagger 用秒，资源/定位仍用毫秒。
- Runtime 创建暂停时间轴并预置最早段落初态；同属性顺序段落允许，重叠明确拒绝。当前不开放 `to/from/call/add`、外部时间轴、回调、插件、无限重复及作用域外目标，不能将窄接口描述成 GSAP 全库支持。
- 视觉规范身份包含稳定元素路径、区间、属性、缓动与标签；资源目标绑定使用 root 内稳定 key，不包含挂载计数。捕获的 visualMode 直接传入适配器，与系统偏好和声音许可分离。
- 动作签名从实际加载的 GLB accessor 字节重建，与 Backend `animation_analysis_version=2` 共享夹具对拍；同名同长度的动作替换也会令旧引用失效。
- 可读海报优先引用视觉末尾的标签，避免修改错峰数量或时长后固定 `poster.atMs` 越界。窗口预览使用交互预览作用域并默认固化海报；`applyPoster` 只控制预览，放映挂载始终准备动画初态，在切页过渡结束后开始播放，不能先显示海报再回零。捕获/导出/缩略图仍由静态就绪协议采样海报，降动效放映在零点使用可读视觉状态。海报必须处于真实计划的 `0–durationMs` 范围内，不能额外加等待值或静默截断。
- 时间轴初始化与静态准备纳入 `render-ready` 内容检查：只等待目标画布内的实例，卸载注销；捕获、导出、缩略图静默准备并采样海报。失败通过有界 `contentExceptions` 传给 Renderer，保留 code/fieldPath/trackId；页面诊断返回 error，截图拒绝成功产物，Backend 不得继承编译通过结果。此检查不代替动态播放验收。
- 单页异步预览须等待主画布的实际模块挂载状态，再收集时间轴初始化结果；双帧或占位画面不能作为内容就绪依据。时间轴缺失或播放受阻保留错误状态，但用户仍可手动前后翻页，离场清理媒体并作废旧页回执。

正式契约继续遵守[运行与捕获契约](./runtime-contract.md)中的唯一所有者、策略独立、身份与发布围栏。产品规模和性能预算留后续复核，不从第一轮历史数字默认为已冻结。
