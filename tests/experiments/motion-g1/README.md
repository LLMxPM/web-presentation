# Motion G1 隔离浏览器验收夹具

从仓库根目录运行：

```powershell
node tests/experiments/motion-g1/run.mjs
```

可追加 `A08` 等场景名片段定向运行。脚本从正式 Runtime 源码加载 `usePageTimeline.v1`、媒体适配器、ModelViewer 和旧媒体会话；生成固定 WebM、WAV、GLB，使用回环随机端口与独立 Chromium，不启动或重置平台服务。临时素材放在系统临时目录，退出时删除；每场景截图与 `result.json` 写入 `.tmp/motion-g1/`，不入库。

覆盖 A03、A04、A06–A10、A12、A13 的**本地 Runtime 行为**：DOM 布局与乱序采样、双 GLB 实例及相机隔离、真实媒体时钟和 Range 定位、主/次要媒体缓冲与 optional 加载失败降级、缓冲后用户暂停、无手势 autoplay 拒绝及手势恢复、有声媒体拖动不补播、主媒体交接、旧媒体所有权、降动效与静态作用域、捕获桥与固化帧。无手势尝试由页面加载脚本自行发起，避免 Playwright 的 `evaluate` 附带用户激活；WebGL 像素比较使用元素截图，避免非保留 drawing buffer 的 `toDataURL()` 空图。

普通场景模式不覆盖 Backend 票据、跨域素材鉴权、远程 Renderer 请求/回执、项目放映和 `timeline_end`、PNG/PDF/PPTX 导出或双窗口演讲者模式。独立 soak 模式覆盖指定的 100 次挂载清理和受控媒体循环，但不替代以上跨端发布验收。A13 只核对本地捕获桥，不据此关闭远程截图验收。完整映射与剩余项见[验收计划](../../../docs/developer/runtime-integration/motion/acceptance.md)和[G1 覆盖映射](../../../docs/developer/runtime-integration/motion/g1-automation-coverage.md)。

## 挂载清理对比与生产预览

默认 `MOTION_RUNTIME_MODE=development` 使用隔离 Vite dev server。设置为 `production` 时，脚本会用 Vite `build()` 编译该实验入口，再以 Vite `preview()` 服务真实生产产物；不是在开发服务器上用 `define` 模拟生产常量。两种模式均使用相同 WebM/WAV/GLB fixture 中间件（支持 HEAD、Range 和慢速分块响应）。生产构建输出在运行期临时目录，退出时清理。

`MOTION_SOAK_MOUNT_SCENARIO` 选择 100 次挂载/卸载样例，支持 `A03-dom-layout` 和 `A04-model-instances`；未设置时默认 A04。`MOTION_SOAK_MS` 控制随后媒体循环的目标时长，比较挂载清理时可设为短时值：

```powershell
$env:MOTION_RUNTIME_MODE = 'production'
$env:MOTION_SOAK_MOUNT_SCENARIO = 'A03-dom-layout'
$env:MOTION_SOAK_MS = '1000'
node tests/experiments/motion-g1/run.mjs --soak
$env:MOTION_SOAK_MOUNT_SCENARIO = 'A04-model-instances'
node tests/experiments/motion-g1/run.mjs --soak
Remove-Item Env:MOTION_RUNTIME_MODE, Env:MOTION_SOAK_MOUNT_SCENARIO, Env:MOTION_SOAK_MS
```

开发模式下执行同样两组命令（先移除 `MOTION_RUNTIME_MODE` 或将其设为 `development`）。每个 A04 循环会等两个 GLB 实例都进入 `ready` 再卸载，并跨两个绘制帧后采样；A03/A04 都在卸载和清空探针后读取 V8 heap、DOM 计数、RAF/计时器和 WebGL 活跃 context。`soak-result.json` 每 10 次记录一次指标，`result.json` 标注实际运行模式及 A04 的 ready 计数。每次运行会覆盖这两个结果文件，需要留存对照结果时先复制到不同文件名。`MOTION_SOAK_HEAP_SNAPSHOT=1` 可在完成挂载阶段后写出堆快照供定位；快照较大，仅在需要时启用。A04 的保留堆已定位为 Three.js 模块级 DFG LUT 通过共享纹理监听持有渲染器，释放共享纹理后回收；这是库层保留，不是应用闭包泄漏，详见[G1 覆盖映射](../../../docs/developer/runtime-integration/motion/g1-automation-coverage.md#a04-保留堆结论)。
