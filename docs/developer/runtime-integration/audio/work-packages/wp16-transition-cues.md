# WP16：切页开始事件与方向 cue

状态：待实施。阶段：M2。主责：Runtime transitions。

## 前置与输入

前置完成：[WP15](./wp15-audio-cue-engine.md)。

## 修改范围与交付

- 为 `PageTransitionHost` 增加 typed `started` 事件，包含 generation、from/to、direction 和 effect。
- 只在接受真实不同页面的新 generation 后发出；初次挂载、同路径、失败导航和被合并的中间跳转不发出。
- shell 将 direction 映射到 `transition.forward` / `transition.backward` 并调用 transition channel。
- 快速导航时新 cue 替换旧 cue；视觉 effect=none 仍可播放真实翻页 cue。
- 导航控件默认不叠加 interaction cue，避免一次动作双声。

## 完成标准

- [ ] 前进、后退、快速连跳、同路径、reduced motion 和离场中断有组件/宿主测试。
- [ ] cue 触发与实际 transition generation 一致，不通过 Router watch 猜测。
- [ ] 没有绑定或播放失败不改变 settled、导航和放映状态。
- [ ] Presenter audience 唯一触发，console 不重复发声。

建议提交标题：`WP16：接入切页方向音效`。
