# 固定 GSAP 适配层：Luna 收口任务包

这是研究 SDK，不是已经公开的 Runtime Kit。使用 GSAP 3.15.0、Vue 3.5.34。只写分配给你的 `candidates/<id>.vue`，中文注释与文件头功能说明。不要运行测试、自行修补多轮，不读其他候选、测试、旧研究答案或报告，不委派。完成一个任务即停，由父智能体保存原始代码再测；失败最多收到一轮有界反馈。

允许读取本任务包、`sdk.ts`、`api-types.ts`、`resource-plan.ts` 和固定模板 `../motion-luna/BenchStage.vue`；如需查原生 API，可查 GSAP 公开类型或官方 <https://gsap.com/docs/v3/GSAP/Timeline/>。不能读取 visual.ts、测试断言、fixtures/ 或其他候选。修改/复用/修复任务可读自己文件中预置的种子源码。

## 使用方式

从 `../sdk` 导入 `BenchStage`、`useGsapStory`、`seconds` 和所需类型。`props` 类型为 `StoryProps`，保留 detailStartMs/modelFile/badClip。建立 stage ref，调用 `useGsapStory(stage, props, ctx => definition)`，`defineExpose` 返回控制对象；模板只放 `<BenchStage ref="stage" />`。

ctx 仅含本实例 root、只读资源摘要 `assets` 和 `resources()` builder，不含媒体或模型控制对象。`ctx.assets.clip` 提供 index/signature/name/durationMs。资源桥接自动处理准备、实际播放、定位与释放，你不要重写这些能力。

definition 形状为：

```ts
return {
  plan, // resources() builder 的 build() 结果
  visual(timeline) {
    // 在已有 GSAP 时间轴上追加原生视觉定义。
  },
}
```

builder 的精确方法签名见 api-types.ts/resource-plan.ts。三条资源的稳定 id 为 voice/model/demo：旁白从0开始，model 为查询到的片段，demo 为视频；所有资源时间为毫秒。clipRef 使用查询得到的 index/signature，badClip=true 时仅将 signature 改为 'stale'，不要吞校验错误。

Runtime 自动将资源 id 登记为视觉标签，所以动画可以直接插到 `'model'` 或 `'demo'`。GSAP 的原生参数仍是秒，使用 `seconds(ms)` 做转换，例如 duration: seconds(400)；不手写 ms/1000。Runtime 已创建暂停时间轴、限定作用域、建立初始状态，且拥有静默采样、固化、卸载；**你只追加视觉定义，不自行创建控制器，不调用 play/seek/kill/revert，不另起 RAF，不直接控制 audio/video/模型**。不要用 any/ts-ignore 或手写插值绕过类型与候选库。

## A：首次生成的固定故事

- voice 从0开始；model 默认 `props.detailStartMs ?? 1200`，片段时长来自摘要；demo 在 model 结束后200ms开始，只用源视频1000—3000ms。通过命名 after 关系表达后继。
- `.title`：0—400ms，opacity 0→1、y 32→0。
- 三个 `.card`：从600ms起，每项300ms，错峰100ms，opacity 0→1、y 24→0。
- `.clip-caption`：model开始时，400ms，opacity 0→1。
- `.demo-caption`：demo开始时，400ms，opacity 0→1、y 32→0。
- 全部线性，开始前保持初态，结束后保持终态。保留 props 的起点覆盖；旁白和前三卡不受 model 起点修改影响。暂不编排 callout。

## B：局部修改

你自己的文件已放入通过 A 的种子。仅将默认 model 起点从1200改成1700，保留 props 覆盖、全部视觉和资源行为。不要改其他内容。

## C：复用段落

你自己的文件已放入通过 A 的种子，默认起点仍为1200。用同一个函数追加两组入场：`.callout-model .chip` 和 `.callout-demo .chip` 各三个，分别在对应资源开始后100ms起；每项200ms、错峰80ms、线性 opacity0→1、y12→0。复用同一份动画定义，不复制两份；保留原有故事。

## D：错误恢复

你自己的文件已放入通过 A 的种子并注入一次 selector 拼写故障，这是评测器制造的，不算你的首次生成错误。行为反馈为：clip-caption 在0ms透明度为1，预期0；在 model 开始后200ms透明度为1，预期0.5。请依据反馈与自己源码修复，保留原有故事，不降低校验或吞错误。
