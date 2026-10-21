# WP01 可复现技术实验

2026-10-21：此目录保留第一轮有限执行器实验，不再代表已完成整体选型。当前按[编排创作夹具](../motion-authoring/README.md)比较 GSAP、Anime.js、Motion 与 WAAPI，本轮不重跑这里的性能测量。

内部验证页，不是 Runtime Kit API。只使用独立测试浏览器、临时 HTTP 端口与 `.tmp/motion-wp01`，不连接开发数据库、不改系统动效设置。

在仓库根运行：

```powershell
New-Item -ItemType Directory -Force .tmp/motion-wp01/deps | Out-Null
Set-Content .tmp/motion-wp01/deps/package.json '{"private":true,"type":"module"}' -Encoding utf8
pnpm --dir .tmp/motion-wp01/deps --ignore-workspace add gsap@3.15.0
node tests/experiments/motion-wp01/run.mjs
node tests/experiments/motion-wp01/probes/correction.mjs
```

GSAP 只装在忽略的实验目录，生产依赖、根锁文件不变。Three.js、Vite 和 Playwright 复用仓库安装版本。脚本先生成 WAV、自包含骨骼 GLB 和反例，再由浏览器绘制帧号画面、随附 ffmpeg 编码 30fps WebM，分别构建两个执行器的离线静态包。第二个临时源站提供带票据、HEAD/Range/CORS 的素材；它是受控跨域夹具，不代替 Backend/Runtime/Renderer 的产品验收。

参考环境为 Windows + 已安装 Microsoft Huihui Desktop 离线语音，以及 Playwright 的 Chromium/ffmpeg。其他平台默认使用提示音替身，不自动声称中文旁白已验证；可通过 `WP01_FFMPEG` 指定兼容 ffmpeg。视频由固定帧编码生成，不依赖实时时钟录制。

第二条 Node 命令复用已构建包，给辅助视频人为注入 400ms 偏差，检查硬校正后恢复，并在实际播放中 dispose。它单独记录源码 hash 和结果，不混入正常稳态漂移预算。

执行结果、样本 hash、设备与浏览器信息、逐次测量和截图写到 `.tmp/motion-wp01`。设置 `WP01_RUN_LABEL=final-1` 会额外保存带标签的结果；`WP01_REUSE_VIDEO=1` 可复用已生成视频。媒体与 GLB 可重新生成，不提交二进制；逐次测量汇总只留本地，不随仓库提交。退出时关闭本次浏览器与测试服务。G0 结果与冻结预算见[验证记录](../../../docs/developer/runtime-integration/motion/wp01-results.md)。
