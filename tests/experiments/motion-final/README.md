# GSAP 固定适配模板与 G0 收口验证

日期：2026-10-21。主线已选择 GSAP，用户明确确认许可没有问题。本轮只收口创作模板和交付功能，不继续横向选库，不比较性能，不开放 Runtime Kit。

`sdk.ts` 只传窄资源摘要、局部 root 和资源 builder；`visual.ts` 统一创建作用域/暂停时间轴、登记资源标签、建立 fromTo 初态、静默采样、固化与释放。GSAP 原生视觉参数仍用秒，`seconds(ms)` 是集中转换入口；资源与 transport 继续使用毫秒。旧 GSAP v2 duration 位置签名明确拒绝。原型支持本题显式 fromTo 轨道，不代表任意插件、回调或全库能力已开放。

评分前参考页自检发现了未来轨道初态问题及重载类型问题，均在模型评分前修正，记录在本地 `evidence/adapter-selfcheck/`（不随仓库提交）。最后一次自检通过后，八份模型评分使用的输入完全相同，hash 可在运行时复核。原型会预置 from 状态并接管 immediateRender，因此模型写 false 也不会使页面失去初态；该参数属于适配层控制范围。

八个 `gpt-6-luna`、medium、`fork_turns: none` 新上下文：A 首次生成、B 延后默认段落、C 同函数复用两组错峰、D 基于有界错误修复，各独立两次。B/C/D 使用同一份通过 A 的种子，D 只注入一次 selector 拼错。每个任务禁止模型测试，交付后先封存再评分，最多一轮反馈；实际八个首次提交均通过，没有修复轮。初始约定为至少7/8首次、8/8在一次反馈内；这是创作小样，不能代替正式 G2 或统计显著性比较。

源码、任务与输入 hash、种子、派发提示、依赖、失败记录和汇总写入本地 `evidence/`，不随仓库提交；仓库只保留 `protocol.json`、`task.md`、候选和可重跑脚本。各上下文共享文件系统，读取范围通过指令约束，不能宣称 OS 沙箱隔离。A1 自述额外查阅了共享 types.ts（任务包未列出但 api-types 直接引用的契约文件），记录为边界说明；未发现借用其他候选答案，不能据此宣称完全审计了每次读取。

环境沿用[完整故事夹具](../motion-story/README.md)的固定依赖和自有媒体。重新测试当前候选应使用独立研究副本或未占用的阶段名：

```powershell
node tests/experiments/motion-story/prepare-assets.mjs
node tests/experiments/motion-final/evaluate.mjs --case=a1
```

`evaluate.mjs` 默认排他写入本地 `evidence/`，不会覆盖旧记录；历史结果不随仓库提交。

裁剪与构建入口：

```powershell
node tests/experiments/motion-story/prepare-assets.mjs
node tests/experiments/motion-final/prepare-production.mjs
pnpm --dir .tmp/motion-final/production --ignore-workspace install --prod
node tests/experiments/motion-final/production.mjs
```

production 结果也采用排他写入，应在新的研究副本运行。它是真实裁剪安装的最小执行包，保持 GSAP/Vue/Three/Vite/Vue插件/TypeScript 为生产依赖，vue-tsc 为被裁掉的开发依赖。第一次研究包误裁 TypeScript 的失败及修正保存在本地证据归档；正式 Runtime 已把 TypeScript 放在生产依赖，本轮未改正式包或根锁文件。

验证从裁剪包实际解析 Vite/插件和所有打包库模块；先运行真实 SFC，再构建，在只提供 HTML/JS/CSS 的源站验证八个页面，无 Vite、源码、node_modules 或互联网回退。另验证静态包中的旁白 ended 时钟交接、裁切视频终帧和播放中卸载。不统计耗时、包体、帧率或内存。

这不代替完整 Runtime 生产镜像、Backend 票据、Editor 预览、远程 Renderer、双窗口和 G1/G2。原始 GLB/音视频与生成产物留在 `.tmp`，不提交。选型及后续边界见 [G0 决定](../../../docs/developer/runtime-integration/motion/g0-decision.md)。
