# Luna 独立 SFC 创作试验

日期：2026-10-21。根据用户要求，通过 `collaboration.spawn_agent` 显式指定 `gpt-6-luna`、medium、`fork_turns: none`，分别创建四个上下文。比较 GSAP/Anime.js × native 资源计划/builder，共四个首次样例；不比较性能，不调用业务 AI 接口或数据库。

固定[任务包](./task.md)与[协议](./protocol.json)；每阶段源码、派发提示和结果写入本地 `evidence/`，不随仓库提交。四个候选分别只写自己的文件，不能读既有答案、其他候选和测试；可查指定契约及本库官方文档/类型。这是共享文件系统上的指令约束，没有操作系统级读取隔离。没有模型内部版本、seed 或 token 统计，不能宣称大样本可重复排名。

每个阶段先封存源码，再执行严格类型与独立浏览器检查；首轮禁止模型自行测试修补。一阶段最多一轮有界错误反馈，修复仍由原 Luna 完成。父模型实现测试夹具，未代写或修正候选。任务 A 一轮反馈后仍失败的候选停止，不再参加 B/C/D。

| 阶段 | 任务 |
| :--- | :--- |
| a0 / a1 | 首次实现；最多一轮反馈后的修复 |
| b0 | 仅把默认模型起点 1200 改到 1700，后继顺延 |
| c0 | 同一函数复用两组 callout，各三项错峰入场 |
| d0 / d1 | 统一注入 `.clip-caption` 拼写故障；一轮反馈后恢复 |

d0 的失败是评测器制造的，不能混入模型生成错误。注入前后 hash、规则和次数单独保存在各候选 `injection.json`。为验证真实静默行为，测试期间通过候选库的公开时间控制方法，在实际时间轴插入一个计数回调；不改候选源码，不执行媒体或业务操作。检查记录 DOM opacity/位移、视频帧、骨骼、乱序恢复、双实例、PNG 固化、过期 clip 与资源控制权。媒体时钟/播放本身由前一轮已验证的共享 SDK 提供，本轮没有让 Luna 重写 transport。

首轮评分前补齐了 SDK 的 Draft 类型重导出，以满足任务所需类型；未修改候选，不计为模型修复。其后评分输入保持不变，hash 验证涵盖全部阶段。

环境沿用[完整故事夹具](../motion-story/README.md)的隔离依赖和原创素材。只启动临时回环端口与独立 Chromium，退出时关闭；无需启动业务服务或重置数据。本地 `evidence/environment.json` 冻结实际执行时的依赖、根锁文件与素材 hash；重复核对不会拿新生成的素材覆盖历史身份。测试当前候选需先按完整故事夹具准备素材，再使用一个未占用的阶段名；封存阶段采用排他写入，不覆盖旧证据：

```powershell
node tests/experiments/motion-story/prepare-assets.mjs
node tests/experiments/motion-luna/evaluate.mjs --candidate=gsap-builder --phase=z0 --detail=1700 --callouts=true
```

历史阶段源码是各阶段的 `candidate.vue.txt`，只保留在本地证据目录。`candidates/anime-native.vue` 保留失败后的真实版本，其余三个为最终 Luna 修复版本；不要把故意保留的研究失败样例算成生产回归或自动加入 Runtime 构建。历史精确重放应在独立研究副本把对应源码放回相同 candidates 路径，用新的阶段名执行；不要覆盖工作区最终候选。

结论、限制及 Runtime 接口建议见[Luna 创作结果](../../../docs/developer/runtime-integration/motion/luna-authoring-results.md)。没有修改生产依赖、Runtime Kit manifest 或公共能力。
