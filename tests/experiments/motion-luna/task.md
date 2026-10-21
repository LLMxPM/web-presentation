# Luna 编排创作对照：固定任务包

这是独立模型创作研究，不是生产 Runtime API。请使用中文注释，文件头写功能描述，只编辑分配给你的候选 `.vue` 文件。首轮完成即停止，不运行类型检查、浏览器测试或自行迭代。不得读取其他候选、既有 GsapStory/AnimeStory/visuals、测试断言和研究结论；只能读本任务包、`sdk.ts`、`BenchStage.vue`、`../motion-story/types.ts`、`../motion-story/use-story.ts`、`../motion-story/plan.ts`。如需查库 API，可查本候选官方文档和本候选发布包的类型，不读另一候选的文档/实现。不要委派其他智能体。

使用 Vue 3.5.34 的 `<script setup lang="ts">`。候选引擎及资源路线由初始消息指定，禁止换引擎或路线。不要用 any、ts-ignore、关闭类型检查或自写 DOM 插值代替候选引擎。

## 提供的边界

从 `../sdk` 导入 `BenchStage`、`useStory`、`compile`、`storyBuilder` 与所需类型。候选文件固定放在 `candidates/`，所以 import 为 `../sdk`。Vue 根组件只需 `<BenchStage ref="stage" />`，在脚本创建 stage ref，再通过 `useStory(stage, props, factory)` 创建并 `defineExpose` 控制对象。

props 为 `{ detailStartMs?: number; modelFile?: string; badClip?: boolean }`。factory 接收已经准备完毕的真实 Assets，返回 `{ plan: Plan; visual: Visual }`。`useStory` 负责资源准备、采样、播放、错误与卸载，候选负责计划和原生视觉定义。

Assets 有：

- `elements.root` 为本实例 HTMLElement；全部选择器限定此作用域。
- `clip: { index, signature, name, durationMs }` 为查询得到的真实 GLB 动作信息，不猜名字或签名。
- `voiceDurationMs`、`videoDurationMs` 来自真实媒体。
- 资源和 transport 已实现，不要直接控制 audio/video、Mixer 或建立第二套 RAF/时钟。

Visual 必须提供三个函数：`sample(ms)` 按绝对毫秒定位且不触发业务回调；`freeze()` 保持当前可见样式并停止原生动画；`dispose()` 最终释放、恢复作用域。全部动画在创建后等待 transport 采样，不能自行播放。任意先后顺序的 sample 应得到相同状态。

## 任务 A：首次编写

1. 三条资源轨道，稳定 id 为 `voice`、`model`、`demo`。旁白从 0 开始；动作从 `props.detailStartMs ?? 1200` 开始，时长使用实际 clip；视频在动作结束后 200ms 开始，只用源视频 1000—3000ms。
2. clipRef 取查询结果 index/signature；当 `props.badClip` 为 true 时仅把 signature 换成 `'stale'`，保留校验错误，不吞掉错误。
3. DOM 目标：`.title` 在 0—400ms 从 opacity 0、y 32 到 opacity 1、y 0；`.card` 共三个，从 600ms 起错峰 100ms，每个 300ms，从 opacity 0、y 24 到最终正常状态。
4. `.clip-caption` 在动作开始时用 400ms 从 opacity 0 到 1；`.demo-caption` 在视频开始时用 400ms 从 opacity 0、y 32 到最终状态。所有效果使用线性缓动，结束后保持，开始前保持初态。
5. 首轮暂不编排 `.callout-model .chip` / `.callout-demo .chip`，这些目标留给后续修改任务。
6. 动作起点变更时，视频与两个字幕的关系自动随定义重建；旁白与前三卡保持原来的时间。不要写死动作两秒或旁白四秒。

### native 资源路线

使用 `compile(assets, drafts)` 构建三条资源轨道。Draft 的形状见 types.ts：`{id,type,target,start,...}`，其中 type 分别 voice/clip/video，target 分别 voice/model/video。作者显式计算视频起点，start 使用 `{atMs}`。同时把资源插入点映射到原生视觉时间轴，禁止用 `.call(() => video.play())`。

### builder 资源路线

使用 `storyBuilder(assets)` 的链式 voice/clip/video/build，资源关系采用命名 after。精确签名见 plan.ts。DOM 仍由你在本 SFC 内调用候选库编排，禁止导入已有视觉 helper。从 `plan.get(id).startMs` 取得视觉插入点，避免重复手工计算后继时间。

## 依赖

- GSAP 候选固定 `gsap@3.15.0`，只从 `gsap` 导入。官方入口：<https://gsap.com/docs/v3/GSAP/Timeline/>、<https://gsap.com/docs/v3/GSAP/gsap.context/>。
- Anime.js 候选固定 `animejs@4.5.0`，只从 `animejs` 导入。官方入口：<https://animejs.com/documentation/timeline/>、<https://animejs.com/documentation/scope/>。

两组使用相同的资源桥接和输出契约；提供的任务包没有给出完整引擎实现。完成后只报告已写文件、查阅过的允许来源及你认为仍不确定的点，不声称已测试通过。
