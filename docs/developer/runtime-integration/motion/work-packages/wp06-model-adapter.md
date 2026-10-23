# WP06 三维动作适配器

状态：完成（2026-10-23 首期收口；真实 WebGL 两实例与静态帧证据见 [G1 映射](../g1-automation-coverage.md)）。主责：Runtime model3d。前置：[WP03](./wp03-transport-targets.md)。

## 输入与落点

复用 GLB 解析缓存、SkeletonUtils 实例克隆、相机配置和静态帧句柄。动作执行拆入 model3d/motion，不把全部职责继续加入 ModelViewer。

## 交付

- 为每实例创建独立 AnimationMixer/action 状态，支持单片段裁切、rate、有限重复、结束保持或还原。
- 模型整体变换应用在源场景外的实例包装节点，不覆盖 clip 内部骨骼/节点动画。
- 按绝对时间重建姿态，更新骨骼与世界矩阵后显式绘制；暂停和静态上下文没有持续 RAF。
- 动作目标通过当前资源与真实片段校验；替换失效时返回定位清楚的错误，不隐式取第一个片段。
- 共享缓存只保留不可变资源，实例动作、骨骼与可变材质状态隔离；释放 mixer/action 不误释放其它实例资源。
- 扩展静态帧状态描述，包含动作时间、循环位置、结束姿态与整体变换；相机仍沿用现有实例视角。

## 验证与通过条件

真实 WebGL 覆盖 A04、A05、A09、A13：两个实例不同姿态、有限循环边界、模型整体转动与内置动作并行、乱序 seek 和上下文丢失。

同一模型不同动作时间必须得到不同且正确的静态帧身份；100 次进出/重播的清理证据按验收计划记录，规模/性能预算在后续复核，G0 未将历史数值冻结。

## 不包含

动作混合、部件拆解、相机轨道、骨骼重定向、新动作生成与物理模拟。

## 实施记录

- 代码版本与 GLB 样本身份：`runtime/src/core/motion/model-adapter.ts`、`runtime/src/runtime-kit/internal/renderers/model3d/motion/motion-contract.ts`；ModelViewer 新增每实例 Mixer、整体包装节点与 `__runtimeModelMotionHandleV1` 句柄。
- 实际命令、结果、状态/帧与资源释放证据：`pnpm --filter web-runtime-vue exec vitest run src/core/motion`，WP06 6 项通过；假句柄验证片段索引/名称/时长失效、裁切重复映射与 reduced 结束姿态。
- 首期收口（2026-10-23）：真实 WebGL 已覆盖 A04 双实例不同姿态/单实例隔离/显式相机、A05 三维替换后旧签名 stale、A13 真实骨骼 GLB 指定状态帧；100 次双 GLB 进出每轮 ready，活跃 context/canvas 为 0。100 次挂载的渲染器保留根因已定位为 Three.js 模块级 DFG LUT，转 [G2-06](../g2-followups.md)；WebGL 上下文丢失/恢复未单独演练，转 G2-07。
