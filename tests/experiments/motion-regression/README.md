# Motion 实施评审回归

从根仓执行 `node tests/experiments/motion-regression/run.mjs`。要求已有 pnpm workspace 依赖及 Playwright Chromium/ffmpeg；脚本不安装依赖、不启动平台服务、不读取或重置业务数据。

脚本在回环随机端口启动隔离 Vite，直接加载正式 Runtime 模块与公开 `usePageTimeline.v1` 入口，结束时关闭浏览器和服务。使用本仓视频生成器及 Backend/Runtime 共享 GLB 字节夹具，验证：

- 系统 reduced 偏好下显式 full 截图采样的真实 opacity 与桥接回执。
- 延后视频不提前播放、到点播放、暂停、精确定位、重播与完成后暂停。
- 真实 GLTFLoader 对 LINEAR、STEP、CUBICSPLINE 的解析签名与 Backend 一致。
- 页面卸载和未处理浏览器异常。

视频、截图和 JSON 结果写入 `.tmp/motion-fix-browser/`，不入库；重新执行会更新该目录中的测试产物。单元回归另外覆盖 HTTP 环境缺少 SubtleCrypto、乱序定位、主时钟重播、重复挂载身份与属性冲突。

此脚本仅提供本地 Chromium 集成证据，不覆盖远程 Renderer、跨域票据/HEAD/Range、双窗口、生产镜像、长时间循环或八任务模型基准，不能作为 G1/G2 关闭依据。
