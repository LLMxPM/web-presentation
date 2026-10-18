# WP09：`media_end` 聚合与错误恢复

状态：待实施。阶段：M1。主责：Runtime。

## 前置与输入

前置完成：[WP07](./wp07-media-purpose-session.md)、[WP08](./wp08-narration-lifecycle.md)。

## 修改范围与交付

- 统一旁白、视频和 content 音频在 `media_end` 下的参与集合，全部非循环参与目标结束后再推进。
- 无参与目标继续按 `delay_ms` 回退；loop 媒体不阻塞但仍受暂停与清理。
- 明确 autoplay blocked、网络/解码 error、超时、重试、下一页和停止的状态转换。
- timer 到达时允许中断旁白并翻页；manual 下旁白结束不翻页。
- 多旁白等契约错误不得进入无限等待。

## 完成标准

- [ ] 单旁白、旁白+视频、content audio、loop 和动态媒体有状态机测试。
- [ ] blocked 后用户手势重试可以继续并最终完成 `media_end`。
- [ ] 错误/超时后用户仍能导航，清理后无旧媒体继续播放。
- [ ] 现有视频 `media_end` 回归全绿。

建议提交标题：`WP09：统一旁白与 media_end 恢复`。
