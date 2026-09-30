# M03 Lite 2C4G 容量基线（探索性）· 2026-09-30

> **状态**：空闲 + 混合负载已采集；容量门保持开放（开跑前无已批准 P95 阈值）。  
> **候选**：`a06120e` + F5/F6/F7/F9 修复（镜像 `sqlite-lite-f9fix` / `renderer:m01-f9dbg`）。  
> **拓扑**：真双容器（platform-lite + renderer，独立网络）。  
> **机器**：2C / 3.8 GiB + 4 GiB swap · `/data` 50G。  
> **时区**：UTC。

## 1. 配置

| 项 | 值 |
| :--- | :--- |
| 空闲窗口 | 600 s，每 15 s 采样（35 点） |
| 混合负载 | 300 s，**5 用户**，并发 3 |
| 操作 | 截图 / 页面更新(PATCH) / 构建 ZIP |
| 打点 | `DATABASE_WRITE_PATH_METRICS_ENABLED=true` |
| 阈值 | **无预批 P95**；本报告为探索性基线 |

## 2. 混合负载结果

| 指标 | 值 |
| :--- | :--- |
| 操作总数 | 截图 **36** · 页更 **29** · 构建 **17**（共 82） |
| 成功率 | **100%**（0 错误） |
| 延迟 P50 | **6.37 s** |
| 延迟 P95 | **97.96 s**（构建拉高；截图单独更快） |
| 延迟 max / mean | 113.9 s / 20.5 s |
| 写冲突 / busy_timeout | **0 / 0** |
| SQL 300s 增量 | total 50142（~167/s）· read 47424 · write 2718（~9/s） |
| SQL avg / max | 4.48 ms / 655 ms |
| tick P50 / P95 | 515 ms / 597 ms |
| 负载停止后队列 | 全部 pending/running = **0**（已收敛） |
| 运行态 | 166 keys · 2.06 MB · capacity_rejections=0 · sweep 无失败 |
| page_screenshot 状态 | succeeded 37 · failed 4（4 条为 F9 调试遗留，本跑 0 失败） |

## 3. 资源峰值（GiB）

| 阶段 | platform-lite | renderer |
| :--- | :--- | :--- |
| 空闲 | 0.73 | 0.20 |
| 混合 | **1.77** | 0.51 |

- 4 GiB 内存内：混合峰值合计约 2.3 GiB，**无 OOM**（swap 使用约 110 MiB）。
- 对照历史单容器 Runtime RSS ~1.4 GiB：双进程拓扑下 Backend 侧峰值可控。

## 4. Lite 状态 drill（baseline）

| 项 | 结果 |
| :--- | :--- |
| 启动 | 通过（需强 Fernet/管理员口令，脚本已补） |
| idle 采样 | keys=0 / bytes=0 / container 1.51 GiB |
| round-1 | keys=20 / bytes≈6.9 MB / container 1.55 GiB |
| create_project_preview | **失败** `RUNTIME_STATE_CAPACITY_EXCEEDED` |

**M03-F1（开放）**：drill 在约 6.9 MB / 20 keys 时项目预览写入触发容量拒绝。预算默认 128 MiB / 单项 16 MiB，总占用远未到顶——疑似**单项超限**或**容量记账/错误映射**问题，需对照 `runtime_state` 写入路径与 large 页面源体积。

## 5. 结论（探索性）

1. **2C4G 双容器形态可承载 5 用户 / 并发 3 的混合负载**，成功率 100%，无锁冲突、无悬挂队列、无 OOM。
2. P95 主要由构建 ZIP 拉高；截图与页更 P50 约数秒级。若要定 SLA，建议拆分操作类型统计。
3. SQLite 写路径在本负载下 **write_conflicts=0、busy_timeouts=0**，未触发方言竞争压力。
4. 容量门**保持开放**：需先锁定延迟阈值并处理 M03-F1，再决定是否把「5–10 人 / 并发 3」升格为承诺。

## 6. 证据

- `m03-report.json` — 汇总
- `idle-samples.json` / `mixed-samples.json` — 时间序列
- `metrics-before-mixed.json` / `metrics-after-mixed.json` — 打点对账
- `lite-drill-baseline.log` — drill 失败现场
