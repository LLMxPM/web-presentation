# WP07：媒体用途与活动页会话

状态：待实施。阶段：M1。主责：Runtime。

## 前置与输入

前置完成：[WP04](./wp04-runtime-kit-asset-audio.md)、[WP06](./wp06-m0-integration.md)。

## 修改范围与交付

- 扩展 `PageMediaSession` target 状态，读取 `data-runtime-media-purpose`，未标记媒体按 content 兼容。
- 为每个稳定的真实放映页创建会话，不再只在 `advance.mode=media_end` 时创建。
- 保留 generation 围栏、MutationObserver、原生事件和 play Promise 作为真实状态来源。
- 区分“参与完成判定”“具备自动播放资格”“仅受暂停/清理管理”三个维度，避免用 loop 或 autoplay 属性替代语义。
- 检测多个 narration 目标并返回有界错误，不同时播放。

## 完成标准

- [ ] content/narration、loop、动态增删和元素换源有单测。
- [ ] 旧页面的 audio/video 行为不变，未声明 purpose 时兼容。
- [ ] dispose 后旧 generation 事件不会进入新页面。
- [ ] 本包不接页面 ready 自动播放，也不修改推进策略。

建议提交标题：`WP07：扩展活动页媒体用途与会话`。
