# M05 版本与升级回滚 · 2026-09-30

> **机器**：38.14.63.47 · 4C / 7.8 GiB · Docker 29.8.1  
> **N**：`a06120e` + F5–F9 + M04-F1/F2 + 指纹 409 修复  
> **N-1**：`4c7eee8`（2026-09-29，W01 前一稳定点）· DB head `20260926_0100`  
> **N 镜像**：`platform-m04` / `web-runtime-vue:m04` / `renderer:m01-f9dbg`  
> **N-1 镜像**：`platform-n1` / `web-runtime-vue:n1`（worktree `/data/wp-n1`）  
> **隔离库**：`web_presentation_m05n1`（从主库拷贝，专供 D/E/中断演练）

## 1. 版本清单

| 组件 | N | N-1 |
| :--- | :--- | :--- |
| Git | `a06120e` | `4c7eee8` |
| Alembic head | `20260930_0100` | `20260926_0100` |
| 新增 migration | `20260929_0100`（`process_owner`）、`20260930_0100`（drop `lease_generation`） | 无 |
| Runtime Kit | `1.0.0` | `1.0.0` |
| 渲染协议 | `internal/render/v1` | 同 |

## 2. 组合结果

| 组合 | 定义 | 结果 | 证据 |
| :--- | :--- | :--- | :--- |
| **A** | N 全量 | **通过** | 截图 job 5/6、构建 job 7/8 `succeeded` |
| **B** | N + N-1 Backend 共存 | **条件通过** | 见 §3：**必须先 upgrade 到 N schema**。N + N-1 在 DB@20260930 上登录均 200。**N 在 N-1 schema 上启动失败**（`UndefinedColumnError: ai_agent_runs.process_owner`） |
| **C** | N + N-1 Runtime/Renderer | **条件通过** | Renderer 混池截图成功（m01-f9dbg + m01-a06120e）；N-1 Runtime `healthz ok / kit 1.0.0`，但缺 F6 allowedHosts 时服务名 Host 被拒 |
| **D** | 迁移窗口 | **部分通过** | `20260926 ⇄ 20260930` downgrade/upgrade 可逆。**不支持**「旧 DB + 新 Backend」——N ORM 需要新列，必须先 migration |
| **E** | DB 已迁 N 后回滚 N-1 | **明确拒绝（符合预期）** | N-1 `alembic upgrade/current` → `Can't locate revision identified by '20260930_0100'`。N-1 **应用**在 N DB 上可启动（多余列无害），但不得执行 N-1 迁移命令 |
| **F** | 指纹失配 | **通过** | 失配 **409** `PREVIEW_VERSION_SKEW`；匹配 `1.0.0+dev` → 401 缺 token。**M05-F1 已修**：`sendPreviewError` 曾把 409 收成 500 |
| **中断升级** | 迁移中途杀容器 | **可恢复** | kill 后 revision 仍 `20260926`（事务回滚）；重跑 `upgrade head` → `20260930` 成功 |

## 3. 灰度/升级顺序（实测约束）

```text
1. 备份 DB
2. alembic upgrade head          # N-1 应用仍可跑在 N schema 上
3. 滚动替换 Backend N-1 → N      # 共存窗口：两者均 200
4. 滚动替换 Runtime/Renderer     # 同池指纹须一致；协议 v1 可混 N-1 Renderer
5. 摘除 N-1
```

**禁止**：
- 未 migrate 就启 N Backend（缺列崩溃）
- 对 N DB 执行 N-1 `alembic upgrade head`（revision 缺失）
- 预览池混用不同 `runtime_kit_version`（409）

## 4. 缺陷

| ID | 级别 | 描述 | 状态 |
| :--- | :--- | :--- | :--- |
| **M05-F1** | P1 | `sendPreviewError` 将带 `statusCode` 的业务错误统一收成 500，指纹 409 不可见 | **已修** + 单测 |
| **M05-F2** | P2 | `formatRuntimeVersionFingerprint()` 空 `build_id` 回落 `dev`，与 healthz `build_id:""` 口径不一致 | 记录；比较以 format 串为准 |
| **矩阵文档** | — | 原 B/D 写「N-1 可共存 / 旧 DB+新 Backend」过宽 | **已改** compatibility-matrix.md |

## 5. 结论（M05 门）

| 门 | 状态 |
| :--- | :--- |
| 同版本可完成真实任务（A） | **已验证** |
| 失配明确拒绝、无静默损坏（F） | **已验证**（409） |
| 迁移可前滚/可按序 downgrade（D） | **已验证**（双向 + 中断可续） |
| N/N-1 共存与回滚边界（B/E） | **已验证并写清边界**（先 migrate 再混跑；E 明确拒绝） |
| Runtime N-1 混跑（C Runtime） | **条件验证**（协议同；F6 差异需注意） |
| 滚动无中断 | **不承诺**（普通 Run 仍不跨实例；预览须排空） |

**M05 门：关闭（2026-09-30）**——矩阵可测项均有实机证据或明确拒绝；未覆盖项（完整两阶段业务排空压测）不阻塞「版本边界已定义且可执行」的结论。  
**多副本/混版承诺**：在固定升级顺序与指纹一致前提下可灰度；**不得**宣称任意混版或滚动零中断。

## 6. 证据

- N-1 worktree：`/data/wp-n1`（`4c7eee8`）
- 镜像：`llmxpm/web-presentation:platform-n1`、`llmxpm/web-runtime-vue:n1`
- 脚本：`/data/m05-n1-matrix.py`、`/data/m05-probe.py`
- 隔离库：`web_presentation_m05n1`
- 文档修订：`docs/developer/deployment/compatibility-matrix.md`
