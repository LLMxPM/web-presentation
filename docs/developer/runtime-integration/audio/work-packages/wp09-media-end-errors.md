# WP09：`media_end` 聚合与错误恢复

状态：待验收（聚合与自动化恢复链路完成，真实浏览器联调并入 WP12）。阶段：M1。主责：Runtime。

## 前置与输入

前置完成：[WP07](./wp07-media-purpose-session.md)、[WP08](./wp08-narration-lifecycle.md)。

## 修改范围与交付

- 统一旁白、视频和 content 音频在 `media_end` 下的参与集合，全部非循环参与目标结束后再推进。
- 无参与目标继续按 `delay_ms` 回退；loop 媒体不阻塞但仍受暂停与清理。
- 明确 autoplay blocked、网络/解码 error、超时、重试、下一页和停止的状态转换。
- timer 到达时允许中断旁白并翻页；manual 下旁白结束不翻页。
- 多旁白等契约错误不得进入无限等待。

## 完成标准

- [x] 单旁白、旁白+视频、content audio、loop 和动态媒体有状态机测试。
- [x] blocked 后用户手势重试可以继续并最终完成 `media_end`。
- [x] 错误/超时后用户仍能导航，清理后无旧媒体继续播放。
- [x] 现有视频 `media_end` 回归全绿。

建议提交标题：`WP09：统一旁白与 media_end 恢复`。

## 实施记录

- 代码版本：本工作包所在提交。
- 已实现：`media_end` 只统计 `participating` 目标，循环媒体和冲突旁白不阻塞完成，也没有参与媒体时回退 `delay_ms`；纯循环媒体不会错误进入等待。`blocked`、原生 error、播放 Promise error、超时、重试、下一页和停止沿用 PlaybackController 状态机。manual/timer 下的内容音频由用户控制，单个资源 error 不阻塞整场放映；旁白 error、contract-error 和 media_end 参与媒体错误仍进入统一错误态。
- 已运行：
  - `pnpm exec vitest run src/runtime-shell/playback/usePlaybackHost.test.ts`：31 项通过，含受阻重试后完整翻页、纯循环媒体、旁白+视频和 manual 内容音频错误隔离。
  - Runtime 全量：148 个文件、1178 项通过、3 项跳过。
  - `pnpm --filter web-runtime-vue check` 与触碰文件 ESLint：通过。
- 未运行：真实浏览器 media error、自动播放阻止和 timeout 的实机重试，留到 WP12。
