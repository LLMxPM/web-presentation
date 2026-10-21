# 编排能力与 Vue SFC 创作调研

这是 WP01 重新选型的功能夹具，不是生产 API。比较 GSAP、Anime.js、Motion for Vue 和裸 WAAPI 的原生写法；不采集时间、帧率、体积、内存或性能排名。

同题任务是标题入场、三卡错峰、对象时间代理、段落结束后出现演示；模型段落起点从 900ms 改为 1400ms，后继自动顺延。两个同时挂载的实例检查选择器作用域隔离。对象代理不代表已经实现 GLB 动作/音视频同步。

根目录执行：

```powershell
New-Item -ItemType Directory -Force .tmp/motion-authoring/deps | Out-Null
Set-Content .tmp/motion-authoring/deps/package.json '{"private":true,"type":"module"}' -Encoding utf8
pnpm --dir .tmp/motion-authoring/deps --ignore-workspace add animejs@4.5.0 gsap@3.15.0 motion@14.3.1 motion-v@2.8.0 vue@3.5.34
node tests/experiments/motion-authoring/run.mjs
```

复用仓库 Vue/Vite/vue-tsc/Playwright 工具链。只启动随机回环端口的夹具 Vite 和独立 Chromium，结束即关闭，不接入业务服务和数据。

脚本先执行五个 Vue SFC 的严格类型检查，再验证四条时间轴的整体定位、乱序恢复、双实例隔离、单起点修改与清理，并检查 Motion 模板 props 交互。另验证 Anime.js 和 Motion JS 的 Three.js Object3D 位置/角度映射；不进行 WebGL 渲染，也不验证骨骼 Mixer 或媒体就绪。

Motion JS 当前检索版本为 14.4.0，但与 motion-v 2.8.0 内部的 14.3 核心共存时，Three.js effect 类型出现不同 MotionValue 私有成员冲突。本夹具固定为同发布线 motion 14.3.1；保留原始错误，不使用 `any` 或跳过样例类型检查掩盖。生产集成仍需决定统一入口及支持的版本组合。

结果写入 `.tmp/motion-authoring/results.json`，逐次证据写入本地 `evidence/`（不随仓库提交）。所有样例为本轮作者手工编写；它们证明 API 可用，不构成独立模型的生成成功率。研究结论见[选型补充报告](../../../docs/developer/runtime-integration/motion/authoring-engine-research.md)。
