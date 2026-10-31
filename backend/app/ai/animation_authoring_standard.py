"""文件功能：维护正向 Scene、多序列、模型/媒体实际完成与独立静态呈现的共同创作规范。"""

ANIMATION_AUTHORING_STANDARD = """
## 页内 Scene 与动态效果规范

### 能力与写法

- 先查询 runtime_kit list/detail，按真实返回的版本化 import_path 使用 usePageScene.v1、useStaticPresentation.v1、AssetModel.v3、AssetAudio.v1、AssetVideo.v1、createSceneMediaTask.v1 与 useAudioCue.v2。未查询到的路径不可凭记忆导入。
- 一页只声明一次 usePageScene({ root, define(scene) { ... } })，同一 Scene 可登记多条 scene.visual({ id, role, define(tl) { ... } }) 和 scene.task(task)。挂载只登记，点击播放或正式放映才 prepare/start。每条任务 id 唯一，role 为 blocking 或 ambient；startMs 与 afterTrack/offsetMs 分别表达起始延时和前驱实际完成后顺延，不能同时填写。
- scene.visual 托管 GSAP 的 to/from/fromTo/set/addLabel/call、位置字符串、stagger、回调和页面数值对象，支持 DOM、SVG 和数值驱动。数字滚动用数值对象与 onUpdate；打字机更新本页文本；SVG 描边可直接修改 strokeDashoffset。GSAP 的 duration/位置用秒，Scene 的 startMs/offsetMs 用毫秒。禁止直接 import GSAP、插件或自己创建全局 timeline/ticker；插件包括 DrawSVG、SplitText、ScrollTrigger，不能因为门面支持回调就推断插件已开放。
- 有限 blocking 实际完成才推动 scene_end；repeat:-1 只允许 ambient，无限任务不可作为依赖前驱。DOM/CSS 无限呼吸、Canvas 粒子可作装饰；有限 Canvas 自定义任务 run 必须返回实际完成的 Promise，不能用估计时长伪造完成。不得依赖 GSAP 粒子插件。自建 RAF、计时器、事件、模型数值和文本变化用 scene.onCleanup 或 task context.onCleanup 恢复；内部冻结时自定义任务必须通过 setSuspended 停止有效推进，恢复不补跑后台积压。
- 组件首轮不自行声明页级 Scene；页面通过真实组件实例句柄协调，避免一页多个调度所有者。CSS/浏览器原生动画也必须有独立静态分支，不能绕过本页生命周期修改全局或其它页面。

### 模型、媒体与 cue

- AssetModel.v1 展示静态/手动交互，片段使用 AssetModel.v3 的组件 ref.getHandle()；只有真实首帧就绪才有句柄。查询资源 analysis_metadata.model3d.animations，要求 supported=true，使用真实 index、signature 和 duration_ms。动画数据不代表支持动画播放，不能猜片段名称、索引或签名；资源替换后重新查询。
- scene.task(handle.animation({ id:'action-a', role:'blocking', clipIndex, signature })) 注册动作；第二个动作使用 afterTrack:'action-a'。同一模型实例不能同时运行两个动作；并行需不同实例。只支持正向 rate，不能 seek、倒放或采样。handle.transform/camera 是实例数值副本，visual onUpdate 调 handle.invalidate()；scene.onCleanup(handle.reset) 恢复，不能访问共享材质、几何、骨骼或 Three.js 内部实例。
- AssetAudio.v1 purpose=narration 和 AssetVideo.v1 purpose=automatic 通过 media-ready 暴露目标；显式 scene.task(createSceneMediaTask({ id, role:'blocking', target:()=>mediaElement })) 接管，实际 ended 才完成。purpose=content 仅用户手动播放，不得交给 Scene 自动接管，不在源码写 autoplay。
- 同页最多一个自动发声主媒体；其它自动视频必须 muted。旁白不循环，无限媒体仅 ambient。总静音不改变主媒体数量约束。播放许可受阻时在当前 Runtime/观众窗口点击允许播放；Editor 或演讲者窗口的点击不能代替该窗口的用户手势。全屏成功不能保证发声成功。资源错误与缓冲应按真实失败/受阻处理，不能按 duration 估计结束。
- useAudioCue.v2 返回 playCue('interaction.*') 的 Promise，只等待真实 play 许可回执，不等待短音效结束；cue 不作为主媒体或 blocking 完成目标。不存在绑定、无 provider、静态环境或静音时按返回值处理，不伪造成功或直接构造 Audio。
- 项目放映 schema 4 只有 manual/timer/scene_end、delay_ms、completion_delay_ms 与 loop。scene_end 要有 blocking 目标，完成后可停留零毫秒；timer 到点会停止尚未完成的任务。保持/释放只抑制自动翻页，不暂停 Scene、声音或改写项目配置。

### 独立静态态

- 同一个 root 声明 useStaticPresentation.v1 的 default/poster/unsupported。default 是完整可读默认模板；poster 用模板或响应 AbortSignal 的 prepare 生成独立海报；unsupported 附短原因。capture/export/thumbnail 不执行 Scene 或快进、定位、采样模型/媒体来取帧。
- 默认样式保持正文完整可读，有限动画保留完成态，定位与动画使用不同包裹层。静态分支不创建 Canvas RAF 或自动播放媒体；模型静态渲染遵守其独立资源契约。PPTX 不保留网页动画。
- STATIC_PRESENTATION_UNAVAILABLE 表示内容没有可用静态态，截图状态为 unavailable，不可重试，不覆盖已成功布局诊断。资源缺失、解码错误、Renderer 断连或超时属于资源/执行失败，不能伪装为 unsupported 或 skipped；pending、skipped 和 failed 也不能当成 ready。
- 响应 prefers-reduced-motion 时只减弱本页视觉运动，不能据此静音或伪造任务完成；保留可读布局。不能把整页统一 opacity:1 导致装饰覆盖正文，也不修改用户系统偏好。

### 创作与复核

1. 查询当前 Runtime Kit、项目配置、真实资源与动作索引/签名。一个联合作品应包含数值、打字机、SVG、DOM/CSS/Canvas 粒子、两个真实模型动作、旁白和 cue；有限目标与装饰角色清楚。
2. 源码创建/修改走页面 Mutation Job，等待终态并读取最终源码与校验结果；CodeCheck 与页面诊断继续经过受信 Renderer，不能自行启动浏览器替代服务验证。不要重复调用自动写入已执行的校验。
3. 默认截图/诊断附图使用独立静态态；不提供任意动作时刻截图。截图只能证明静态像素与布局，不能证明播放、声音、许可或 scene_end 推进。
4. 实时预览检查播放/停止、实际完成依赖、停止清理与 no-preference/reduce。正式放映检查 manual/timer/scene_end、保持/释放和本地许可。未实测时逐项写明，不能将单测或截图宣称为浏览器、音频、WebGL 或多窗口通过。
5. 反馈无动画时先确认 iframe/截图/导出，检查实际 matchMedia、样式与触发时机；无法访问真实环境时明确待核实，不编造系统设置或检测值。
""".strip()
