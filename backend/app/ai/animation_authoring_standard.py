"""文件功能：维护页面与组件共用的动画能力、降动效适配及动态验收提示。"""

ANIMATION_AUTHORING_STANDARD = """
## 页内动画与动态效果规范

### 能力与实现

- 页内元素动效可使用 CSS transition、@keyframes、Vue Transition/TransitionGroup 和页面自身的响应式状态；首次挂载需要过渡时显式使用 appear。数字变化、SVG 路径等可由局部 JavaScript 或浏览器原生动画 API 实现；定时器、requestAnimationFrame、动画实例和事件监听必须在卸载时清理，不修改宿主或其它页面的全局状态。
- 动效应服务于内容表达和操作反馈；入场、强调、退场、错峰与循环按需要选择，不默认让正文和标题反复隐藏重播。定位变换与动画变换使用不同包裹层，避免动画 transform 覆盖居中、旋转等既有布局。
- 图表动效遵循 AssetChart 的真实配置契约，三维模型仍以 AssetModel 当前契约为准，不因 GLB 含动画数据就承诺播放。不得假设 GSAP、Motion、Lottie 等依赖或未登记的 Runtime Kit 动画组件已经可用。
- 页内动画与项目 none/fade/push 翻页过渡分别控制。当前没有统一的页内步骤时间轴或“下一步逐项出现”契约，放映暂停也不会统一暂停任意 CSS/JavaScript 动画；自行实现的交互只能按已实现、已验证的范围说明。

### 静态基线与减少动态效果

- 先保证无动画时的稳定可读状态，再叠加动效；核心内容不以 opacity: 0、隐藏或画布外位置作为唯一基础样式，也不依赖 animationend 回调才出现。有限入场动画应保留结束状态；无限循环只用于适合循环的内容或装饰，并提供可读静态状态。
- 默认响应 prefers-reduced-motion 偏好，可在 no-preference 分支启用完整动效，或在 reduce 分支减弱/关闭动效并恢复静态可读状态；规则只作用于本页或本组件的动效元素，保留布局所需的定位变换，不能把全页统一设为 opacity: 1 导致闪光、遮罩等装饰覆盖正文。
- prefers-reduced-motion: reduce 是系统/浏览器向网页报告的偏好信号，不会自动禁止所有 CSS/JavaScript 动画；网页是否减弱或停止由自身样式/逻辑决定。同一环境中，一页响应 reduce 而另一页未适配，便可能分别呈现静态与动态，不能据此判断平台兼容性不同。

### 排查与验收

- 用户反馈实时预览没有动画时，先确认查看的是实时 iframe、截图/缩略图还是导出；有真实环境访问能力时，在实际渲染 iframe 检查 matchMedia('(prefers-reduced-motion: reduce)').matches，再检查样式/关键帧是否加载、animationName/animationDuration/animationPlayState、触发时机及延迟；transition 同时检查过渡属性与前后状态。命中 reduce 且计算样式为 animation: none 时，应说明是页面按偏好降动效，不直接归因于 Vue scoped、Runtime 或浏览器不兼容，也不把删除降动效适配作为默认修复。
- Windows 关闭动画效果或开发者工具模拟可能产生 reduce；只能按真实检测结果说明原因，不能仅凭媒体查询就断言是哪项系统设置被谁修改。无法访问用户实际环境时，明确待核实项，不编造检测值，不擅自修改用户系统或浏览器偏好。
- Renderer 截图/诊断上下文主动使用 reduce，截图还会禁用动画；静态导出对有限原生动画有等待/收尾处理，无限循环不会一直等待，任意 JavaScript/Canvas 动画不保证统一冻结，PPTX 不保留网页动画时间轴。截图成功或静态画面不能证明动效已播放或实时预览也被禁用；动态验收需在实时预览分别检查 no-preference 与 reduce 下的表现，未实测时明确说明。
""".strip()
