# 历史 JSON 创作草案

状态：历史候选，未选为唯一创作入口。2026-10-21 的[G0 决定](./g0-decision.md)已采用原生 GSAP 视觉＋资源 builder；下文只保留此前 JSON tracks 草案，WP02 不应直接照此建立第二套完整视觉 DSL。当前方向见[创作契约](./authoring-contract.md)，执行约束见[运行契约](./runtime-contract.md)。

## 入口与定义归属

拟新增 `usePageTimeline.v1`，通过 Runtime Kit manifest 返回真实版本化 import path。一次调用接收 `definition` 与 `bindings`，返回只读状态及 `play/pause/resume/restart/seek/dispose` 控制接口。页面根部仍使用页面组件或 DefaultContainer。

- `definition` 是 JSON 兼容数据，只含标识、数值、标签、轨道及策略，不接受函数、任意表达式字符串、资源 URL 或 Three.js 对象。
- `bindings` 是页面内 Vue ref 到目标 key 的映射，不序列化进定义。资源组件继续通过真实 `name` 引用资产；定义不再重复保存 name 或 src。
- 当前实际页面最多一个时间轴；可复用组件可提供带命名空间的轨道片段，由页面合并。组件不得偷偷建立第二个全局播放者；组件预览使用独立宿主测试该片段。
- 定义保留在现有源码版本中；不新增第二套时间轴持久化数据。Runtime 解析后校验并生成规范计划及摘要，Backend 不通过执行 Vue/JavaScript 来解析定义。
- 类型化帮助函数可以生成同一份定义，但首期文档只推荐一种写法，避免模型在多种等价 DSL 间切换。

## 顶层结构

| 字段 | 约束 |
| :--- | :--- |
| `schemaVersion` | 固定 `page-timeline.v1` |
| `id` | 页面内稳定标识，1–64 字符；不含资源身份或票据 |
| `clock` | `{source:'monotonic'}` 或 `{source:'media', trackId}`；媒体必须为有限的 required 同步轨道 |
| `labels` | 标签到非负整数毫秒的映射；仅作为定位锚点，不自动执行事件 |
| `tracks` | 下述判别联合数组；轨道 id 唯一，顺序不决定同一时刻的覆盖优先级 |
| `poster` | `{atMs}` 或 `{atLabel, offsetMs?}` 二选一；省略时取 required 有限轨道的结束状态 |
| `motionPreference` | `system/reduced`，默认 system；源码只能跟随或收紧偏好，不能强制 full |
| `reducedState` | 可选，选择器形状同 poster；默认 poster，用于模型/变换的静态姿态 |

所有公开时间使用整数毫秒，速度使用有限数值；Three.js 的秒单位只在内部转换。未知字段、布尔冒充数值、NaN、Infinity、未知枚举和越界值拒绝。

## 轨道公共字段

每条轨道具有 `id`、`type`、`target` 和 `start`。`start` 严格为以下一种：

```json
{"atMs": 0}
```

```json
{"atLabel": "detail", "offsetMs": 200}
```

```json
{"afterTrack": "open-product", "offsetMs": 200}
```

`afterTrack` 只允许非负 offset，不支持隐含位置符号；共享标签即并行。编译器检测循环依赖、重复 id、未知目标和无穷结束依赖，输出每条轨道的绝对起止时间与定位信息。

`required` 默认 true：失败或缓冲阻塞相关播放，参与时间轴完成判定。`required=false` 的可选装饰失败给 warning，不阻止播放，不得作为 clock 或 afterTrack 的完成依赖。首轮提出每页 64 总轨道、32 总目标、有限主时长 30 分钟；当前只作为历史候选，待创作路线确定后再复核，不作为本轮选型依据。

主时长取 required 有限轨道的最大结束时间，至少有一条这样的轨道；optional 轨道超过主时长时停止，不延迟完成。durationMs 为正整数且不超过主时长预算；easing 首批为 linear/ease-in/ease-out/ease-in-out，默认 ease-out，执行器只转换这些明确枚举。

## 首期轨道

| type | 目标与字段 | 约束 |
| :--- | :--- | :--- |
| `enter` | DOM；`preset`、`durationMs` | 预设首批为 fade、fade-up；核心内容基础样式可读 |
| `tween` | DOM；`from/to`、`durationMs`、`easing` | 只支持 opacity、独立包装层的 x/y、等比 scale、2D rotate；属性显式给定 |
| `model-clip` | 模型；`clipRef:{index,signature}`、`inMs/outMs`、`rate`、`repeat`、`endPose` | 一个实例同时最多一条片段；endPose 为 hold/reset，默认 hold |
| `model-transform` | 模型整体；`from/to`、`durationMs`、`easing` | position、归一化 quaternion、正值等比 scale；作用在源模型外的实例包装节点 |
| `media` | audio/video；`inMs/outMs`、`rate`、`repeat`、`muted` | 文件媒体、可定位且时长有限；音频只允许已开放的 narration 同步使用 |
| `text-cue` | DOM 文本槽；`text`、`durationMs` | 有限字符串、纯文本写入；不接受 HTML，首期不自动生成字幕时间 |

补充约束：

- 入出点缺省为源片段或媒体的完整有效范围；实际时长必须在准备阶段解析，不能从文件大小猜测。`0 <= inMs < outMs <= sourceDurationMs`。
- rate 首期候选范围 0.5–2，repeat 为有限正整数。结束时间按裁切长度、rate、repeat 计算；不得把 `Infinity` 放入主时长。
- 有限视觉轨道默认保持最终状态。无限装饰仅允许 enter/tween 的独立 `repeat:'infinite'`、`required:false` 组合；不进入主时长，poster 按其有限采样时刻确定。
- 同一目标同一属性的时间区间重叠默认报冲突；不同目标或不同属性允许并行，不采用“后添加覆盖前添加”。片段内部动作与模型整体包装变换分层执行。
- 资源版本及片段必须经过真实查询。clipRef 使用源索引和动作签名；签名由规范化采样器、通道、目标绑定及必要初始姿态摘要派生，算法随分析策略版本固定。片段名称只作展示，索引处签名不一致时不得静默选第一个动作。
- 动作摘要沿用现有资源详情，新增 duration_ms、signature、supported 与 unsupported_reason；旧未分析摘要不伪装成可播放。file_hash 描述当前资产版本并用于写入/发布前复核，不作为 Vue 源码里永久锁定旧文件的地址。
- 替换资源仍影响当前及历史页面预览：同索引、同动作签名的兼容替换继续使用当前文件，截图身份随新 file_hash 更新；不兼容替换报过期引用，重新查询并修改源码。不能偷偷加载历史文件，也不自动换到别的索引。
- 媒体主轨道从 0 开始、rate=1、repeat=1；首期主媒体不在运行期间切换。辅助轨道按照 [时间映射](./runtime-contract.md) 跟随。
- 最多一个有声同步媒体。存在旁白时同步视频必须静音；音量继续遵守现有项目音量和会话静音。独立用户内容媒体不自动加入时间轴。
- 不允许用任意回调补造业务状态或声音。现有 `useAudioCue.v1` 保持独立；首期不增加 cue 轨道。

## 目标绑定与版本

`AssetAudio.v2`、`AssetVideo.v2`、`AssetModel.v2` 拟复用现有内部渲染器并增加时间轴目标句柄。没有时间轴认领时保留原用途与手动播放行为。v1 继续保留，不让旧页面因新增编排而开始播放。

公共句柄只允许类型检查、描述和交给时间轴认领；页面不取得私有 src、原生媒体控制权、Object3D 或 AnimationMixer。DOM 目标使用局部 Vue ref；资源目标使用对应组件 ref。同一个目标只能被一个会话认领。

v2 不复制资源解析、音量或鉴权逻辑。新增公共项必须满足 Runtime Kit 版本命名、manifest、previewSchema 和三端正反例约束；不把 shell 播放控制条公开为页面组件。

## 模型编写示例

以下为约定形状示意，真实 import 由 WP10 发布的 manifest 提供；`queriedClip` 的 index 和 signature 必须来自真实资源查询。

```ts
// 文件功能：声明标题、模型动作、视频和旁白共用的页内编排。
const timeline = usePageTimeline({
  bindings: { title: titleRef, product: modelRef, voice: audioRef, demo: videoRef },
  definition: {
    schemaVersion: 'page-timeline.v1',
    id: 'product-intro',
    clock: { source: 'media', trackId: 'voice-track' },
    labels: { intro: 0, detail: 4200 },
    tracks: [
      { id: 'voice-track', type: 'media', target: 'voice', start: { atMs: 0 } },
      {
        id: 'title-in', type: 'enter', target: 'title',
        start: { atLabel: 'intro' }, preset: 'fade-up', durationMs: 400,
      },
      {
        id: 'open-product', type: 'model-clip', target: 'product',
        start: { atLabel: 'detail' },
        clipRef: { index: queriedClip.index, signature: queriedClip.signature },
      },
      {
        id: 'demo-track', type: 'media', target: 'demo',
        start: { afterTrack: 'open-product', offsetMs: 200 },
        inMs: 2000, outMs: 7000, muted: true,
      },
    ],
    poster: { atLabel: 'detail', offsetMs: 600 },
  },
})
```

例中的主媒体结束后，若仍有 required 轨道未完成，逻辑时间按运行契约转为单调时钟继续；主媒体区间内不因动画更长而截断旁白，也不在主媒体结束后提前翻页。

## 校验与可修改性

WP02 的机器事实源拟落为 `runtime/src/runtime-kit/manifest/schemas/page-timeline.v1.json`，类型由该 Schema 派生或用同一批用例对拍。Schema 与计划编译结果不在多端手工复制。

Backend 能直接校验提交给 API 的结构化捕获选择器及资源元数据；对于 Vue 中的任意绑定表达式，由受信 Renderer 内的 Runtime 解析和校验。Backend 不用正则推断任意 TypeScript 对象，也不启动浏览器。

计划编译后的错误至少包含 code、timelineId、trackId、fieldPath 和有界 message。模型改“模型动作晚 200ms”应只需修改该轨道 start，后继时间由编译器重算。标准示例覆盖新增、修改、错误恢复和降动效，示例不演变成第二套能力目录。
