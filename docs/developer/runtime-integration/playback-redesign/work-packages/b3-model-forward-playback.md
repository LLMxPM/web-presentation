# B3 三维正向片段播放

状态：工程完成（2026-10-30，实例正向动作、v3 句柄、模块拆分与开发回归通过；真实 WebGL 待 C3）。主责：Runtime model3d。前置：[B2](./b2-completion-aggregation.md)。出口：GB。

三维是四条线中保留最多、改动最集中的一块：资源能力、实例克隆、首帧探针与静态帧采集全部保留，只把「任意时刻姿态」换成「实例自己的正向播放」。

## 交付

- 拆分 `ModelViewer.vue`（1393 行）为加载与实例、相机与交互、首帧就绪、WebGL 生命周期、静态帧采集五块；保持自包含 GLB 资源身份、受保护读取、SkeletonUtils 独立场景克隆、解析缓存引用计数、视角隔离和同一同步任务内重绘后读回 PNG。
- **决定 renderer 所有权**（每实例、每页共享或池化）并记录理由：Three.js r186 模块级 DFG LUT 经共享纹理的 `dispose` 监听持有渲染器，A04 实测 100 次双 GLB 进出约 +10 MiB JS 堆而活跃 context/canvas 归零。本包给出决策与观测口径；修复或接受的结论由 C3 收口（承接 G2-06）。
- 每个模型实例独立创建 Mixer/action，按 RAF 的正向 delta 播放真实 GLB 片段；有限片段结束发一次完成事件并注册为 `blocking`，无限片段只作 `ambient`；离页停止 RAF、action 与实例资源。
- 页面通过实例句柄注册片段、整体变换与相机动画；GSAP 可驱动实例级数值并请求重绘。片段索引与签名只用于开始前失效校验，不以名称猜测片段，不用于每帧状态证明。
- `AssetModel.v1` 保留静态展示与可交互职责；暴露实例句柄的公开组件按 `.vN` 纪律新增，同步 manifest 与 Backend 导入白名单；删除 `AssetModel.v2`。
- 不直接暴露共享几何或材质给页面写入（当前缓存共享，直接交给页面会让同资源其它实例串色或串动作）；动作混合与材质/骨骼脚本留给 D2，Three.js 对象树粒子不在范围。

## 开发验收

模型资源、相机、静态截图接线与 PPTX 媒体块的单测和无浏览器集成测试继续通过；测试有限结束、无限循环、替换后片段失效、快速离页、重新进入、双实例不同动作、静态路径不推进 Mixer；两个实例互不影响，卸载一个不释放另一个的共享资源。renderer 所有权决策与观测口径写入本卡片。

真实 WebGL 的首帧、动作隔离、上下文丢失/恢复、静态 PNG 与反复进出后的资源曲线统一在 C3 验证（承接 G2-06/G2-07）；不以 jsdom 的 canvas 假对象充当截图证据，C3 给出 A04 的修复或接受结论。

## 分批记录

第一批基于 B2 `0ee2621` 拆出查看器组合式协调器、相机、实例纹理/灯光、首帧证明与静态采集模块；ModelViewer 组件由 1393 行降到 128 行。保持现有独立相机、GLB 引用计数、纹理预热和同步重绘/PNG 读回语义。开发验证为模型相关 9 文件 73 项通过及 Runtime check 通过。旧动作句柄尚待下一批替换，不作 B3 完成或实机结论。

第二批基于 `a3b6a33` 移除 Viewer 的旧 applyAt 句柄，新增独立 Mixer/action 的真实正向任务，完成以 Three.js finished 回报；正向 delta 支持有限重复、无限 ambient、冻结基线重置与离页/资源替换清理。prepare/start 均校验索引和真实签名，旧资源保存的句柄失效。新增 AssetModel.v3 并删除 v2；v1 继续静态/交互渲染。v3 通过 ref.getHandle() 暴露有限数值副本、片段任务和 invalidate/reset，不暴露共享几何、材质、Mixer 或骨骼。模型变换只作用实例包装节点。

WebGL 生命周期独立模块合并隐藏、尺寸、交叉可见性和上下文丢失状态；一种恢复事件不得提前解除其它来源的暂挂。恢复必须重新取得真实帧证明。离页同时取消等待就绪的 RAF，迟到 Promise 受加载令牌围栏约束。模型静态 PNG 与 PPTX 媒体块仍使用独立静态路径，不推进 Mixer。

开发验证：模型、资源组件、静态帧 13 文件 109 项通过；Kit manifest 16 项、根仓 manifest/仓库约束 68 项和 Backend Kit 契约 6 项通过；Runtime check/build 通过。完整 Runtime 首轮其余 1457 项通过、3 项跳过，仅两条旧 v2 manifest 断言失败，更新后对应文件 16 项通过；后续 B4/B5 收口再跑完整集合。首轮正向单测修正了浮点终值精确比较，以及纯 ambient 错配 scene_end 的测试夹具，没有用假 finished 替代 Mixer 实际完成。

## Renderer 所有权决策与 C3 观测

采用**池化，使用中每实例独占**：同时显示的模型绝不共用 renderer、canvas、相机或 Mixer；卸载后清空 render lists、动画循环与 GL 状态，空闲池最多 4 个，超额或已丢失上下文的 renderer 销毁。这样保持静态同步重绘/读回与多实例隔离，同时减少反复构造 Three.js renderer 带来的共享 DFG LUT 监听持有风险。池中驻留最多四个上下文是明确成本，不宣称此决策已经修复 A04 的 JS 堆增长。

内部 `readModelRendererPoolStats()` 提供 active/idle/created/disposed/peakActive/maxIdle。C3 在固定候选、固定模型和同一 GC 口径下记录基线、双模型反复进出至少 100 次后的差值：借用 active 离页归零、idle≤4、DOM canvas 归零、创建数趋稳，同时记录真实 WebGL context、JS 堆与 GPU 曲线。计数器只证明所有权调用，不证明浏览器实际回收；DFG LUT 的 A04 修复或接受结论仍由 C3 根据最终镜像/产物给出。旧 core/motion 模型适配器与摘要契约已无 Viewer 消费，由 C2 全仓删除；AI/CLI 旧 v2 指引由 B5 更新。
