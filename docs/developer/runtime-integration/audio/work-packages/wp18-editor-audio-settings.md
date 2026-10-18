# WP18：Editor 项目音频设置

状态：待实施。阶段：M2。主责：Editor。

## 前置与输入

前置完成：[WP13](./wp13-audio-settings-storage.md)、[WP14](./wp14-cue-snapshot-packages.md)。实施前读取根目录 `DESIGN.md`。

## 修改范围与交付

- 在项目展示配置中增加独立“音频”分区，编辑 master/narration/effects 音量。
- 配置前进/后退系统 cue 和 `interaction.*` 绑定；资源选择器仅列 active audio。
- 支持显式试听、替换、清空、未保存提示、加载/错误/空态和继承说明。
- 展示最终增益的可理解摘要；试听尊重当前 master/effects 设置并在 dialog 关闭时停止。
- capability 未开放时隐藏或只读，不提交旧 Runtime 无法执行的配置。

## 完成标准

- [ ] 保存、重新打开、清空、并发错误和旧客户端数据映射有组件测试。
- [ ] 选择非 audio 或跨 workspace 即使伪造请求也由 Backend 拒绝。
- [ ] 小屏、滚动、键盘操作和试听停止符合设计规范。
- [ ] Editor 生成类型、类型检查、单测和构建通过。

建议提交标题：`WP18：增加项目音频与 cue 配置`。
