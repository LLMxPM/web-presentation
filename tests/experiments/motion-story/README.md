# 完整故事 SFC 功能对照

日期：2026-10-21。WP01 研究夹具，比较 GSAP 3.15.0 / Anime.js 4.5.0 的原生桥接、有限资源 builder、JSON tracks 三种写法，共六组合。Motion 沿用[上一轮](../motion-authoring/README.md)的 Vue 声明式参照，裸 WAAPI 退出主编排候选。本轮不采集性能、包体或独立模型生成成功率。

先按上一轮说明准备隔离候选依赖，并安装仓库现有工具链与 Playwright Chromium。在根目录执行：

```powershell
node tests/experiments/motion-story/prepare-assets.mjs
node tests/experiments/motion-story/run.mjs
node tests/experiments/motion-story/probe-events.mjs
```

素材完整时复用；需要重建时给第一条命令加 `--regenerate`。只调用旧夹具的素材生成函数，不运行历史性能 runner。Windows 使用已安装的 Microsoft Huihui Desktop 离线合成自有中文文案，其他平台使用提示音时钟替身，不声称完成中文语音验收。视频由浏览器画出带帧号的 180 帧，再由 Playwright 随附 ffmpeg 编为固定 30fps WebM；可通过 `WP01_FFMPEG` 指定兼容 ffmpeg。

故事使用四秒旁白、两秒骨骼 clip、六秒源视频中的 1—3 秒。默认动作起点 1200ms，视频接在动作结束后 200ms，总长 5400ms；将起点改为 1700ms 后总长 5900ms。旁白结束前使用实际音频时钟，正常 ended 后才续走单调时钟。静态定位等待 seeked 与视频解码帧；实时播放不逐帧改写视频 currentTime，正常结束再定位并等待裁切终帧。

`run.mjs` 检查四个编排 SFC 和公共模板的严格 Vue/TypeScript 类型，随后验证六组合的绝对/乱序定位、真实视频像素、两骨骼实例独立姿态、固定状态 PNG 一致、起点修改、过期 clip 反馈及作者修正。另检验正常播放的媒体时钟交接、错误目标/依赖环/越界裁切/无动作/动作目标缺失/同名动作反例，以及播放中卸载的媒体释放。媒体/模型旧 MJS helper 沿用上一轮代码，未宣称纳入严格 TypeScript 检查。

`probe-events.mjs` 单独检查父时间轴静默定位 900ms 时的父子 `.call`：本版本 Anime.js `sync(child)` 仍触发子回调；向同一父时间轴追加段落的工厂写法和 GSAP 原生嵌套均未触发。该探针把观察结果固定为断言，未来升级若改变行为需重审证据。

两个服务都只监听回环随机端口，浏览器为本次独立测试实例，退出即关闭。不启动产品服务、不重置开发数据库、不连接 Backend 或 Renderer。跨域素材使用固定夹具票据及 CORS/Range，并不代表生产鉴权验收。实验没有新增 Runtime Kit 公共能力。

临时原始结果、截图及素材清单写入 `.tmp/motion-story/`，确认后的逐次证据写入本地 `evidence/`（不随仓库提交）。素材可重建，不提交 GLB/WAV/WebM。研究结论见[完整故事与创作入口比较](../../../docs/developer/runtime-integration/motion/story-authoring-comparison.md)。
