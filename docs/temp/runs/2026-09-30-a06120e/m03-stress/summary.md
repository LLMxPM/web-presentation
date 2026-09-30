# M03 并发阶梯压测与瓶颈分析 · 2026-09-30

> 拓扑：真双容器（platform-lite + renderer）· 2C/3.8GiB · `RENDER_GLOBAL_CONCURRENCY=1` · `PAGE_SCREENSHOT_QUEUE_CONCURRENCY=1` · `RUNTIME_VITE_TASK_CONCURRENCY=1`  
> 混合负载：截图 : 页更 : 构建 ≈ 4:2:1 · 16 个测试用户  
> 证据：`stress-report.json` 与各档 `*-samples.json`

## 1. 阶梯结果

| 档位 | 工人数 | 时长 | 截图数 | 截图 P50 | 截图 P95 | 吞吐(截图/s) | 峰值 CPU plat/rend | 峰值 RSS plat/rend | 队列峰值 | 写冲突 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- | :---: | :---: |
| c4 | 4 | 90s | 16 | **18.6s** | 20.2s | 0.18 | 174% / 102% | 1.66 / 0.45 GiB | 4 | 0 |
| c8 | 8 | 90s | 24 | **40.7s** | 43.8s | 0.27 | 167% / 97% | 1.82 / 0.46 GiB | 8 | 0 |
| c12 | 12 | 120s | 33 | **64.0s** | 68.2s | 0.28 | 109% / 118% | 0.86 / 0.55 GiB | 12 | 0 |
| c16 | 16 | 120s | 35 | **87.0s** | 98.1s | 0.29 | 111% / 113% | 0.89 / 0.56 GiB | 16 | 0 |

- 成功率全程 **100%**，无 OOM，SQLite **write_conflicts=0 / busy_timeouts=0**。
- 页更在 c4 仍 ~0.2s；c12/c16 窗口内几乎被截图占满（0 次完成）——不是页更变慢，是**槽位被截图排队占满**。
- 构建 c4：4 次、P50 **56s**（构建 worker 也是单并发）。

## 2. 瓶颈判定

```text
吞吐天花板 ≈ 0.28 截图/s  →  有效服务时间 ≈ 3.5s/张（单槽）
延迟 ≈ 排队位次 × 3.5s + CPU 争用
c16: 16 × 3.5 ≈ 56s 理论  vs  实测 P50 87s（2C CPU 争用上浮 ~55%）
```

| 优先级 | 瓶颈 | 证据 | 说明 |
| :---: | :--- | :--- | :--- |
| **P0** | **渲染单槽**（`RENDER_GLOBAL_CONCURRENCY=1` + 截图队列并发 1） | 吞吐随并发**不涨**（0.18→0.29），延迟近似线性；队列深度=工人数 | 加并发只加排队，不加产出 |
| P1 | **构建单 worker**（`RUNTIME_VITE_TASK_CONCURRENCY=1`） | c4 构建 P50 56s，且与截图抢 Runtime | 构建与预览共用 Vite 调度 |
| P2 | **2C CPU** | c4 时 platform 174%（两核打满） | 单槽下 CPU 已紧；扩槽前需更多核 |
| — | 内存 | 峰值合计 < 2.4 GiB / 4 GiB | **不是**瓶颈 |
| — | SQLite 锁 | 写冲突/busy 均为 0 | **不是**瓶颈 |

## 3. 结论与建议

1. **当前 Lite 默认并发 1 是刻意产品约束**；在 2C4G 上继续加用户只会拉长 P50/P95，吞吐卡在 ~17 张/分钟（截图）。
2. 若目标是「5–10 人顺滑」，单槽 + 3.5s 服务时间意味着 **P50 排队约 (N-1)×3.5s**：5 人约 14s、10 人约 31s——与 c4/c8 实测吻合。
3. **扩吞吐路径**（需改配置/资源，而非调用户数）：
   - 提高 `RENDER_GLOBAL_CONCURRENCY` / `PAGE_SCREENSHOT_QUEUE_CONCURRENCY`（并配 ≥2 Renderer 或单 Renderer 多槽）
   - 提高 `RUNTIME_VITE_TASK_CONCURRENCY` 分流构建 vs 预览
   - CPU：**≥4C** 才有扩槽意义；内存不是约束
4. 产品文档中的「预览并发约 3」与 `RENDER_GLOBAL_CONCURRENCY=1` 不一致——**名义并发 3 实际被渲染槽压成 1**，建议对齐表述或改配置。

## 4. 未做

- 提高 `RENDER_GLOBAL_CONCURRENCY` 后的对照压测（需改 compose 并可能 4C）
- 构建与截图拆分队列的隔离收益
- M03-F1（drill 容量拒绝）仍开放
