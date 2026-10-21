"""文件功能：维护页面与组件共用的动画能力、降动效适配及动态验收提示。"""

ANIMATION_AUTHORING_STANDARD = """
## 页内动画与动态效果规范

### 能力与实现

- 页内元素动效可使用 CSS transition、@keyframes、Vue Transition/TransitionGroup 和页面自身的响应式状态；首次挂载需要过渡时显式使用 appear。数字变化、SVG 路径等可由局部 JavaScript 或浏览器原生动画 API 实现；定时器、requestAnimationFrame、动画实例和事件监听必须在卸载时清理，不修改宿主或其它页面的全局状态。
- 需要统一时钟、音视频定位或三维片段采样时，先调用 `runtime_kit.query`（`list`/`detail`）查询 `usePageTimeline` 与 `AssetVideo.v2`、`AssetAudio.v2`、`AssetModel.v2`。只有查询结果明确返回该能力且可用时，才可按其 `import_path` 创建定义；未返回、`enabled=false` 或只存在于文档时视为未开放，不得凭记忆导入未登记的 Runtime Kit 路径，也不得改用未注册的 GSAP、Motion、Lottie 等动画库。
- 当前时间轴公共入口与三个 `Asset*.v2` 处于内部关闭状态（G2 前不进入普通模型能力目录）。未开放时应继续使用 CSS/原生动画或既有的 `AssetVideo.v1`、`AssetAudio.v1`、`AssetModel.v1` 静态/手动能力，并明确告知用户当前不支持统一页内编排，不伪造已经可用的时间轴示例。
- 可用时，页面只声明一个静态 `definition` 与目标 `bindings`，通过 `usePageTimeline({ root, bindings, definition })` 注册。DOM 轨道 `target` 必须是 `bindings` 的 key；音视频与模型轨道用 `asset` 指向资源逻辑名，并由 `AssetVideo.v2`、`AssetAudio.v2`、`AssetModel.v2` 渲染。定义不接受函数、URL、私有对象或运行中替换；`timelineId` 保持稳定，页面最多一个时间轴，组件片段由页面合并。
- 轨道使用稳定 `id`、绝对 `startMs` 或 `afterTrack`/`offsetMs` 表达并行与顺延；`poster` 只声明默认静态位置，`atMs` 与 `atLabel` 互斥。DOM 首期只支持 `opacity`、`x`、`y`、`scale`、`rotation` 与 `fade`/`fade-up`/`scale-in` 预设；需要其它属性时明确列为未支持，不写无法校验的任意样式。
- 三维片段只使用资源详情 `analysis_metadata.model3d.animations` 中真实返回的动作：`supported=true`，引用其 `index`、`signature` 与 `duration_ms`，裁切终点不得超出真实时长。`supported=false`、未分析、只有动画数量或只凭 GLB 文件含动画数据都不能宣称可播放；动作签名或资源版本变化后必须重新查询，不复用过期引用。
- 动效应服务于内容表达和操作反馈；入场、强调、退场、错峰与循环按需要选择，不默认让正文和标题反复隐藏重播。定位变换与动画变换使用不同包裹层，避免动画 transform 覆盖居中、旋转等既有布局。
- 页内动画与项目 none/fade/push 翻页过渡分别控制。只有放映能力明确声明 `timeline_end`（`advance_modes` 包含且 `schema_version >= 3`）时才能写入该推进模式与 `timeline_timeout_ms`；未声明时写入会被拒绝，应保留 manual/timer/media_end 并明确说明，不得静默替换为 timer。

### 静态基线与减少动态效果

- 先保证无动画时的稳定可读状态，再叠加动效；核心内容不以 opacity: 0、隐藏或画布外位置作为唯一基础样式，也不依赖 animationend 回调才出现。有限入场动画应保留结束状态；无限循环只用于适合循环的内容或装饰，并提供可读静态状态。
- 默认响应 prefers-reduced-motion 偏好，可在 no-preference 分支启用完整动效，或在 reduce 分支减弱/关闭动效并恢复静态可读状态；规则只作用于本页或本组件的动效元素，保留布局所需的定位变换，不能把全页统一设为 opacity: 1 导致闪光、遮罩等装饰覆盖正文。
- prefers-reduced-motion: reduce 是系统/浏览器向网页报告的偏好信号，不会自动禁止所有 CSS/JavaScript 动画；网页是否减弱或停止由自身样式/逻辑决定。同一环境中，一页响应 reduce 而另一页未适配，便可能分别呈现静态与动态，不能据此判断平台兼容性不同。
- 使用 `usePageTimeline` 时，视觉模式由显式参数、调试参数或系统偏好解析；降低视觉运动不等于静音，也不等于触发播放完成。捕获/导出使用独立视觉模式输入，不能通过修改用户系统偏好取得全动效帧。

### 创作与验收流程

1. 读取 `runtime_kit` 能力，确认时间轴与所需 `Asset*.v2` 已开放；未开放则停止统一编排方案。
2. 查询真实资源与动作摘要，记录资源逻辑名、动作 index/signature/duration。不使用猜测的片段名或不存在的资源。
3. 在页面源码中声明唯一时间轴与绑定，通过页面/组件 Mutation Job 写入并等待终态；修改后重新读取最终版本，确认依赖与校验结果。
4. 需要图片时，默认截图只使用页面 poster；临时时间点截图必须通过截图任务选择器并等待任务成功，不得把默认最新截图当作指定动作时刻的证明。当前临时选择器随能力关闭，未开放时明确报告不可用。
5. 静态截图、缩略图和导出只能证明某一确定画面的像素与可读性，不能证明动画已经播放、声音已经播放、自动播放未被拒绝或实时预览也处于 reduce。动态验收需在实时预览分别检查 no-preference 与 reduce，并说明实际观察到的暂停、定位、重播与 timeline_end 结果。

### 排查与验收

- 用户反馈实时预览没有动画时，先确认查看的是实时 iframe、截图/缩略图还是导出；有真实环境访问能力时，在实际渲染 iframe 检查 matchMedia('(prefers-reduced-motion: reduce)').matches，再检查样式/关键帧是否加载、animationName/animationDuration/animationPlayState、触发时机及延迟；transition 同时检查过渡属性与前后状态。命中 reduce 且计算样式为 animation: none 时，应说明是页面按偏好降动效，不直接归因于 Vue scoped、Runtime 或浏览器不兼容，也不把删除降动效适配作为默认修复。
- Windows 关闭动画效果或开发者工具模拟可能产生 reduce；只能按真实检测结果说明原因，不能仅凭媒体查询就断言是哪项系统设置被谁修改。无法访问用户实际环境时，明确待核实项，不编造检测值，不擅自修改用户系统或浏览器偏好。
- Renderer 截图/诊断上下文主动使用 reduce，截图还会禁用动画；静态导出对有限原生动画有等待/收尾处理，无限循环不会一直等待，任意 JavaScript/Canvas 动画不保证统一冻结，PPTX 不保留网页动画时间轴。截图成功或静态画面不能证明动效已播放或实时预览也被禁用；动态验收需在实时预览分别检查 no-preference 与 reduce 下的表现，未实测时明确说明。
""".strip()
