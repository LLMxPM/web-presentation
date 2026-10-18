# WP16：切页开始事件与方向 cue

状态：已实现，待 WP20 真机验收。阶段：M2。主责：Runtime transitions。

## 前置与输入

前置完成：[WP15](./wp15-audio-cue-engine.md)。

## 修改范围与交付

- 为 `PageTransitionHost` 增加 typed `started` 事件，包含 generation、from/to、direction 和 effect。
- 只在接受真实不同页面的新 generation 后发出；初次挂载、同路径、失败导航和被合并的中间跳转不发出。
- shell 将 direction 映射到 `transition.forward` / `transition.backward` 并调用 transition channel。
- 快速导航时新 cue 替换旧 cue；视觉 effect=none 仍可播放真实翻页 cue。
- 导航控件默认不叠加 interaction cue，避免一次动作双声。

## 完成标准

- [x] 前进、后退、快速连跳、同路径、reduced motion 和离场中断有组件/宿主测试。
- [x] cue 触发与实际 transition generation 一致，不通过 Router watch 猜测。
- [x] 没有绑定或播放失败不改变 settled、导航和放映状态。
- [x] Presenter audience 唯一触发，console 不重复发声。

## 实施记录（2026-10-18）

- `TransitionStartedEvent` 在 `PageTransitionHost.show()` 通过同路径与初次挂载检查后、视觉分支前发出，因此 `effect=none`、`disabled` 与 `prefers-reduced-motion` 不改变音频契约；快速导航只有最终被接受的 generation 才发出。
- `RuntimePageStage`、`PresenterPageStage` 透传 `started`；`ResponsiveLayout` 仅在根元素全屏时播放方向 cue，`PresenterDisplayView` 作为观众窗口唯一播放者，控制台保持 thumbnail 无音频。
- 导航控件没有注册全局 click cue，避免与切页 cue 形成双声。
- 已运行：`pnpm exec vitest run src/runtime-shell/transitions/PageTransitionHost.test.ts`（10 passed，包含初次/同路径、前进/后退、effect=none、reduced motion、快速连跳、200 次连续导航与卸载）；`pnpm exec vue-tsc -b` 通过。
- 未运行：双窗口观众真机翻页与快速长按演示留待 WP20。

建议提交标题：`WP16：接入切页方向音效`。
