# 编排引擎与 AI 编写 Vue SFC 的选型补充

日期：2026-10-21。本文保留选型调研过程，曾撤回首轮 WAAPI/G0 判断；后续固定模板与交付验证已选定 GSAP、关闭功能 G0，当前结论以[G0 决定](./g0-decision.md)为准。本阶段只比较能力、创作与集成职责，不比较体积、耗时、帧率或内存。

## 当前判断

当前主线收窄为 GSAP 与 Anime.js；GSAP 优先，Anime.js 保留主要备选，Motion 转为 Vue 声明式/局部交互参照。裸 WAAPI 退出主编排选型，仅保留底层与历史参照。四候选原生能力核对保留在本文；后续的真实旁白、视频与 GLB 六组合结果及静默回调差异见[完整故事研究](./story-authoring-comparison.md)。

本文基础核对基于官方 API、发布包类型和本地功能样例；后续 Luna 两轮小样及交付验证已完成，不宣称某库“AI 生成成功率最高”。GSAP 与默认创作形状已确定，WP02 按最终创作方向正式定义契约。

## 先分清三个决定

| 决定 | 要回答的问题 | 本轮发现 |
| :--- | :--- | :--- |
| 创作入口 | AI 在 Vue SFC 里写原生库、受控 builder，还是 JSON 轨道？ | 这直接决定可写效果、局部修改与提示长度，应先比较 |
| 编排引擎 | 标签、段落、错峰、对象属性、嵌套及定位由谁实现？ | 成熟时间轴能承担较多工作，不能在比较前全部用自建 IR 抹平 |
| Runtime 集成 | 资源、播放许可、主媒体时钟、buffering、骨骼、指定状态捕获由谁负责？ | 这些仍是平台职责，任一动画库都不能单独替代 |

第一轮把候选限制成“暂停对象、每帧写入统一绝对位置”，又只测试 opacity/transform，隐藏了库的原生编排能力。它适合验证执行适配器，覆盖不了“模型写完整演示顺不顺手”。

## 比较对象与版本

Motion 按 motion.dev 家族调研，区分 `motion` 的 JS sequence、`motion-v` 的 Vue 集成和 `motion/mini`；不把 VueUse Motion、React 专用写法或早期 Motion One API 混入同一个候选。

2026-10-21 查询 npm：Anime.js 4.5.0、GSAP 3.15.0、Motion JS 14.4.0、Motion for Vue 2.8.0。本轮 SFC 和 3D 联合夹具固定 Motion JS 14.3.1，与 Vue 包的 14.3 核心同发布线；原因与原始错误见后文。Vue 固定为仓库使用的 3.5.34。生产包与根锁文件未改。

| 能力 | GSAP | Anime.js v4 | Motion JS / Vue | 裸 WAAPI |
| :--- | :--- | :--- | :--- | :--- |
| 时间组织 | timeline、标签、相对位置、重叠 | timeline、标签、相对位置、同步 | sequence、标签、at、重叠 | 单动画时间模型；本题需自行组织组 |
| 段落复用 | 原生嵌套 timeline | 原生 sync 子时间轴/动画 | sequence 片段可展开复用；不等同嵌套子播放器 | 自建计划与控制器 |
| 错峰和关键帧 | 原生 | 原生 | hybrid/JS sequence 原生 | 关键帧原生；错峰需分配 delay |
| DOM 与对象同场编排 | 支持 | 支持 | hybrid 支持 | JS 对象轨道需自建采样 |
| Vue 组件作用域 | context + root + revert | scope + root + revert | useAnimate 自动作用域和卸载清理 | Vue 生命周期中逐项登记/取消 |
| 模板状态、手势和布局 | 需命令式或组件封装；扩展另评 | 需命令式或组件封装；layout 等另评 | motion 组件、variants、手势、layout 为一等入口 | 自建 Vue 封装 |
| 3D 整体变换 | 可驱动对象属性 | 当前有 Three.js adapter | 当前有 motion/three effect | 自建对象插值 |
| GLB clip / 音视频主时钟 | 需 Runtime 桥接 | 需 Runtime 桥接 | 需 Runtime 桥接 | 需 Runtime 桥接 |

表中“原生”依据当前公开入口，不代表已经通过本平台集成验收；“需桥接”不代表该库不能用于此场景。下面分别列出来源与调用上的实际差别。

## GSAP：复杂段落编排的候选

标签、子时间轴和位置参数可在同一控制对象中组合段落；context 能限定 Vue 根节点，并统一撤销。参考 [Timeline](https://gsap.com/docs/v3/GSAP/Timeline/)、[addLabel](https://gsap.com/docs/v3/GSAP/Timeline/addLabel/)、[Vue context 用法](https://gsap.com/docs/v3/GSAP/gsap.context/)。

SFC 内写段落、把段落插到标签处，再统一 seek，是较直接的结构。适合需要多个视效段落反复组合、延迟和重叠的演示页。其可选 SVG/文字等扩展应按具体目标另验证，不能把扩展名存在视为本平台已支持。

创作注意点是秒单位、Vue mounted 后传 `root.value`、作用域内创建对象并在卸载时 revert；当前夹具已严格类型检查及执行。`<` 指最近加入动画的起点、`>` 指其终点。标签或 position 在构建时解析，不能把修改一个运行中标签误认为自动维护所有语义依赖。

当前许可另见 [GSAP 标准许可](https://gsap.com/community/standard-license/)；是否采用应结合最终产品形态确认，不能把“商业免费”泛化为所有可视化构建能力均无限制。本轮不以此直接排除其编排能力。

## Anime.js：应作为主要时间轴候选

v4 的 createTimeline、label、sync、stagger 和 scope 能表达本题段落；JS 对象可和 DOM 一起编排，时间默认以毫秒表示。参考 [Timeline](https://animejs.com/documentation/timeline/)、[子时间轴同步](https://animejs.com/documentation/timeline/sync-timelines/)、[Scope](https://animejs.com/documentation/scope/)、[对象属性](https://animejs.com/documentation/animation/animatable-properties/javascript-object-properties/)。

与本平台拟定毫秒单位相合，Vue 的 `onMounted → createScope(root) → createTimeline → onBeforeUnmount(revert)` 可固定为短模板。以本题判断，它并非只有轻量单元素效果的库；无需先自造完整分组、标签和播放器。

实际遇到的初始化差异：时间轴中未来的 from 状态不会都在创建时立即应用；暂停预览需要显式 `.init()`。补上后，初始状态与乱序定位通过。该行为有[官方说明](https://animejs.com/documentation/timeline/timeline-methods/init/)。还需防止模型混用 v3 的 `anime.timeline()`、v4 的 `createTimeline()`，以及与 GSAP 混淆位置符号：Anime.js 的 `<` 指上一段终点、`<<` 才是上一段起点，见[时间位置](https://animejs.com/documentation/timeline/time-position/)。

当前 4.5 发布包提供 `animejs/adapters/three`，不是只能逐个写 position/rotation；其映射采用角度等约定，可驱动材质、uniform 和实例变换。参考 [Adapters](https://animejs.com/documentation/adapters/)、[Three.js adapter](https://animejs.com/documentation/adapters/threejs-adapter/)。本轮只功能验证 Object3D 的 x 与 rotateY；未据此声称支持 GLB clip。适配器要求避免 Three.js 多份实例，见[官方注意事项](https://animejs.com/documentation/adapters/threejs-adapter/threejs-adapter-common-gotchas/)。

## Motion：SFC 声明式与序列都要比较

`motion-v` 的组件能把状态、交互和布局动画直接写进 template；`useAnimate` 提供作用域与自动卸载清理。因此仅把 Motion 看成 WAAPI 包装会漏掉它对 Vue 创作的价值。参考 [Vue animation](https://motion.dev/docs/vue-animation)、[motion 组件](https://motion.dev/docs/vue-motion-component)、[useAnimate](https://motion.dev/docs/vue-use-animate)。

整页顺序关系可以用 JS/hybrid sequence，包含 labels、at、错峰、对象数值及整体时间控制；不能只用多个 `await animate()` 来代替可拖动的编排，也不能因为它不是 GSAP 的链式嵌套就断言不支持复杂组合。`motion/mini` 不提供完整 sequence/对象能力，不能拿 mini 版本代表全家族。参考 [animate 的 sequence 与 controls](https://motion.dev/docs/animate)。

两种写法适合不同任务：`<motion.div :animate="…">` 对局部交互很直接；需要按旁白时刻统一回放的页面，则必须验证其 sequence 与 Runtime transport 的关系。variants 的父子传播不是跨媒体主时间轴。

当前详细[Three.js 文档](https://motion.dev/docs/three)及发布包提供 `motion/three`、`animate.addEffect(threeEffect)`，可以混合 DOM 和对象变换；官网 animate 概览仍含“早期访问”的说明，存在文档版本差异。本报告以详细入口、安装包导出和功能探针确认能力，不把泛化文案当权限结论。该能力也不自动管理 AnimationMixer、GLB clip、视频解码或资源句柄。

真实版本风险：本夹具混用 JS 14.4.0 与 Vue 2.8.0（内部 framer-motion/motion-dom 14.3）时，Three effect 出现两个 MotionValue 私有类型不兼容的 TypeScript 错误。没有用类型断言掩盖；改用 JS 14.3.1 同发布线后类型和功能均通过。这说明 Runtime 应选定统一入口/受支持组合，不让 AI 在单页随意混装 JS、Vue、旧 Motion One 和 React 导入。原始错误随证据保留；不据此推断所有安装环境都会复现。

## WAAPI：保留执行参照，补足成本需如实计入

WAAPI 提供 effect、currentTime、播放控制和原生关键帧；不直接提供本题的标签、段落依赖和 JS 对象轨道。参考 [Web Animations](https://www.w3.org/TR/web-animations-1/)。

裸 WAAPI 样例因此显式维护开始/结束时间、对象插值、动画列表和组控制。Runtime 当然可以隐藏这些代码，但那意味着平台在承担编排引擎工作，不能在选型时忽略。若未来只开放极少数预设，WAAPI 仍是合理候选；当前用户关注完整编排，应同时评估平台需要重新实现多少能力。

## 同题 SFC 功能核对

完整样例与执行入口见[夹具说明](../../../../tests/experiments/motion-authoring/README.md)，其中含四个原生时间轴 SFC 和一个 Motion 声明式交互 SFC。它们是研发对照，不是当前 Runtime Kit 已允许的 import 或用户可直接调用的新 API。

| SFC | 关键调用形状 | 这个例子让作者写什么 |
| :--- | :--- | :--- |
| [GSAP](../../../../tests/experiments/motion-authoring/GsapScene.vue) | `root.add(detail, 'detail')` | 将原生子段落放到标签，整体控制交给父时间轴 |
| [Anime.js](../../../../tests/experiments/motion-authoring/AnimeScene.vue) | `root.sync(detail, 'detail').init()` | 同步原生子时间轴，显式初始化暂停样式 |
| [Motion sequence](../../../../tests/experiments/motion-authoring/MotionScene.vue) | `animate([{ name: 'detail', at: … }, ...section])` | 用数组片段、标签与 at 描述时间关系 |
| [Motion 模板](../../../../tests/experiments/motion-authoring/PropsScene.vue) | `<motion.div :animate="state" />` | Vue 状态驱动局部交互，另评整体时钟接管 |
| [WAAPI](../../../../tests/experiments/motion-authoring/WaapiScene.vue) | 为每个对象写 `currentTime` 并单独采样时间代理 | 维护组和依赖；若由 Runtime 隐藏，成本归 Runtime |

| 核对项 | 本轮结果 |
| :--- | :--- |
| 5 个 SFC 严格 Vue/TypeScript 检查 | 通过 |
| 标题、三卡错峰、对象时间代理、后继演示 | 四候选通过 |
| 0/200/750/1200/3300ms 整体采样，再走终点和反向回到 t | 四候选状态相同 |
| 同时挂两个实例，只操作左侧 | 右侧样式/对象状态保持独立 |
| 仅将段落起点 900ms 改为 1400ms，重新构建定义 | 四候选后继顺延，总时长由 3400ms 变为 3900ms |
| 卸载和主动清理 | 本题动画对象退出文档，无浏览器脚本错误 |
| Motion 模板 props 点击交互 | x=80、scale=1.1 达到预期 |
| Anime.js / Motion JS Three adapter | t=中点时 x=1、rotateY=45° |

局部修改结果是源码输入改变后重新构建，不是对运行中对象任意改字段都能自动重排。这一组样例本身未覆盖媒体、GLB 与静默回调；后续研究补了真实资源与一个嵌套回调路径，仍不能外推所有插件、回调和生产取帧行为。

## AI 调用顺手程度：比较生成负担，不用代码行数排名

| 观察点 | GSAP | Anime.js | Motion | WAAPI |
| :--- | :--- | :--- | :--- | :--- |
| SFC 生命周期模板 | context 包裹，卸载 revert | scope 包裹，init + revert | useAnimate 或模板组件 | 逐项登记、组控制和取消 |
| 描述“整个段落晚 500ms” | 移段落插入点 | 移 sync 段落插入点 | 修改标签位置，重建 sequence | 改计划起点并重算自建依赖 |
| 容易混淆处 | 秒/毫秒、最近加入段落的 `<` | v3/v4、`<`/`<<`、初始样式 | JS/Vue/React/mini 导入与版本，props/sequence 角色 | 个体 currentTime 不等于组控制，对象轨道需另写 |
| 高层语义仍缺什么 | 真实资源句柄、clip、主媒体、ready、静态采样 | 同左 | 同左 | 同左，另需较完整编排层 |

判断“AI 顺手”至少需要新建、增量修改、错误恢复三组任务。已写好的作者样例只能验证表达性；后续 Luna 小样已保存四个独立上下文的首轮与一轮反馈，三个完成后续修改/复用/修复。它稍支持 GSAP，但不是正式 G2 模型基准，也没有证明广泛成功率排名。

## Runtime 创作入口也需要重开比较

| 路线 | 优点 | 需要核对的代价 |
| :--- | :--- | :--- |
| 原生库 + 薄生命周期/资源桥接 | 保留库的编排语义与生态，模型可沿用熟悉 API | 原生回调、目标、样式和时钟控制面较宽；如何保证捕获、独占媒体和错误定位 |
| 受控 builder + 库执行 | 用命名段落、资源动作和显式依赖减少样板，同时复用成熟引擎 | 需设计少量有语义的方法；不能逐项复制库 API 或无声丢掉关键能力 |
| 完整 JSON tracks（原草案） | 可校验、易输出错误位置和稳定计划 | 错峰/复用/曲线等会否退化成大量重复轨道；平台是否重新实现了过多编排语义 |

完整故事对照后，优先验证“受控作用域 + 原生视觉段落 + 有限资源 builder”。资源依赖可校验，DOM 能力继续复用成熟库；不把完整 JSON 当成唯一的 SFC 创作入口。接口仍未冻结，实验 builder 不是公开 API。

Runtime 应承担资源与 clip 查询、挂载/卸载、目标所有权、autoplay/reduced 策略、旁白主时钟、required buffering、异步 seek/帧就绪、模型实例/姿态、poster/静态采样和诊断。不要让 AI 通过 `.call(() => video.play())` 补造媒体调度，也不要实时逐帧 tween video.currentTime。3D 整体变换和骨骼动作保持明确区分。

后续已经补了同一真实故事的三路线、两引擎六组合，以及 Luna 的生成/修改/恢复小样。六组合作者样例只证明表达性，Luna 小样另行记录真实首轮失败及修复。下一步先确定默认模板和控制边界，并重复创作样例，再冻结 Schema，性能继续后置。

## 证据和当前边界

功能结果、源码 hash 与版本记录在本地研究证据中（不随仓库提交）。Motion 首次版本冲突的原始错误同样只保留在本地研究归档，不设仓库链接。

四候选基础夹具未包含 GLB clip；后续完整故事已补真实骨骼、媒体与固定状态捕获，再补 Luna 四上下文创作小样。尚未跑新的性能基准、生产资源链路、远程 Renderer、正式 G2 模型基准、跨浏览器或部署。未新增生产依赖、未开启 Runtime Kit 能力、未修改用户系统动画设置。

已运行 `node tests/experiments/motion-authoring/run.mjs`：五个 SFC 类型检查、四候选同题功能、Motion 模板交互和两个 Three adapter 探针通过。`pnpm --config.verify-deps-before-run=false run test:repository` 通过（8 文件、63 项）；实验 MJS 解析及 `git diff --check` 通过。生产 package.json 和根锁文件无改动。
