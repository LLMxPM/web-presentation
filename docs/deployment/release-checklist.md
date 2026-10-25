<!-- 文件功能：从归档治理计划提取的尚未闭环事项接续，记录发布待验证事项与证据状态。 -->
# 发布检查与待验证事项

以下事项从 [部署形态收敛与配置治理工作计划](../archive/architecture-2026-09/plans/deployment-form-and-config-governance-plan-2026-10-02.md) 提取，在计划归档后继续追踪。文档归档不代表验收完成。

2026-10-16 文件鉴权修复新增发布条件，详见[文件存储鉴权规划](../developer/runtime-integration/file-storage-auth-cache-plan.md)：

- 配置独立预览主机名的 DNS / TLS，验证 `/runtime/` 与受保护 `/build-artifacts/`；业务 Cookie 不设置父域 Domain，预览域不加入业务 CORS。
- 旧字体桶关闭匿名 ACL / policy，保留 Backend 服务身份迁移读取权限；检查历史绝对 public URL，不能通过重新开放旧入口回滚。
- 排空不兼容 Runtime / Renderer 和构建 attempt；新截图使用内容 hash，旧截图 latest 兼容，不宣称历史表已回填。
- 补齐真实 S3 兼容服务、跨副本、浏览器导出与外部客户端矩阵；采集成本与回源指标后再决定 CDN。
- Editor 私有截图、资源图片、主题 Logo 与字体地址统一对齐实际 API 入口，验证工作台使用 `localhost`、Backend 公开基址使用 `127.0.0.1` 时图片仍能带登录态加载；External API 的绝对文件地址保持原契约。

---

## 1. Renderer / Runtime 镜像拉取验证

**状态**：`v0.3.1` 已发布；ACR 匿名 manifest 与本机 digest 拉取通过，Docker Hub Registry 直连拉取待从非故障网络复核。

2026-10-24 查到两个 Registry 的 platform、Lite、Runtime、Renderer `v0.3.1` 相同 digest；本机从 ACR 按 digest 拉取四镜像，OCI revision 均为 `a94ae57`。Docker Hub 公共标签元数据可读，本机 Registry HEAD 经代理返回 EOF，不能记作直接拉取通过。确切 digest 与升级证据见[动画前版本联合验收记录](../developer/runtime-integration/pre-motion-joint-acceptance.md)。检查脚本 `scripts/contracts/check-compose-images.py` 与 npm script `test:contracts:compose-images` 已就绪。

**下一步**：从可直连 Docker Hub Registry 的 CI 或主机执行匿名 `docker manifest inspect` 与 `docker pull`，同时核对 ACR digest；将结果留在发布流水线。

**原始记录**：归档计划 GAT2。

---

## 2. 镜像可拉取性定时 CI

**状态**：检查脚本就绪，定时 CI 未接入。

`check-compose-images.py` 可独立运行检查 compose 模板引用的所有镜像是否可拉取，但尚未接入 GitHub Actions 定时触发。

**下一步**：将 `test:contracts:compose-images` 接入 GitHub Actions 定时运行（建议每周）。

**原始记录**：归档计划 GAT2。

---

## 3. Lite 合并浏览器后的容量实测

**状态**：口径对齐完成，实测数据待采集。

开发与用户文档已严格对齐为「5–10 人小团队、预览并发约 3，容量验收前为目标规模非 SLA 承诺」。4 长期进程合并故障域与风险接受决策记录在 [Lite 规模与隔离决策](./operations/lite-scale-and-isolation.md)。

**下一步**：实测单容器 4 进程在 2C4G 下的 RSS 峰值与 P95 基线，验证或修订推荐规模。不达标时修改实现或修订文档，不改阈值宣布通过。

**原始记录**：归档计划 M03′。

---

## 4. arm64 实际构建时长、体积和启动证据

**状态**：设计对齐完成，未进行 QEMU 实际构建。

Lite Dockerfile 采用双 venv 独立依赖隔离（D-Dep3），生产流水线通过 Buildx + `cache-scope` 缓存浏览器层与 uv 层。Lite 压缩体积实测 675 MB（amd64），未触发 800 MiB 复审。

**下一步**：在 Release CI 中完成 arm64 构建，记录层体积分解与实际构建时长。若 Release 超时，先用缓存机制解决；仍不达标则重开 D-Dep3 决策（改单 venv + 改写依赖层承诺）。

**原始记录**：归档计划 B4 arm64，风险 R-Dep5。

---

## 5. M1 自动放映能力与 Runtime 配套

**状态**：源码能力已开放（2026-10-17），同版部署验证待执行。

Backend `capabilities.slideshow` 已声明 `advance_modes` 为 `manual`/`timer`、`single_window_auto_play` 为 true；`presenter_auto_play` 与 `capture_auto_play` 仍为 false。该声明只对应当前包含 WP13–WP18 播放控制的 Runtime。

**发布要求**：

- Backend 与 Runtime 使用同版部署；不得把声明 timer/单窗口能力的 Backend 与旧 Runtime 执行池组合后对外宣布支持。
- 已打开的放映窗口保持创建时的不可变快照；回滚应用不重写历史 artifact，也不保证旧版本可以完整编辑新配置。
- 部署后执行真实浏览器计时、暂停/循环和 CLI/MCP 读改写抽查；证据记入 [WP21](../developer/runtime-integration/slideshow/work-packages/wp21-m1-integration-release.md)。

**下一步**：在目标部署拓扑执行同版升级与回滚演练，并记录版本矩阵和实际证据。

---

## 6. 页内动画与时间轴能力开放门禁

**状态**：时间轴与 `timeline_end` 已默认开放（2026-10-22）；G1 已关闭（2026-10-23），G2 未关闭；指定状态截图仍关闭。

首期编排 WP01–WP12 的代码、契约与客户端适配已实施。当前 `TIMELINE_CAPABILITY_ENABLED=true`、`TIMELINE_CAPTURE_SNAPSHOT_ENABLED=false`，放映可执行 `advance_modes` 已含 `timeline_end`；用户文档与顶层 README 已同步。G1 的 A01–A16 已有自动化、隔离 Chromium 与跨端 E2E 证据（见 [G1 映射](../developer/runtime-integration/motion/g1-automation-coverage.md)）；G2 的 Editor + 内置助手 + CLI 联合创作、生产依赖裁剪镜像最终重建、混版/回退、修正版 30 分钟长测与 B01–B08 模型基准尚未完成；长稳中需记录 A04 的 Three.js 模块级 DFG LUT 渲染器保留（活跃 context/canvas 为 0，属库层行为）。MCP 暂不提供服务，不列入本轮发布验证。逐项状态、关闭条件与边界补测见 [G2 遗留清单](../developer/runtime-integration/motion/g2-followups.md)。

**发布要求**：

- 关闭 G2 前，必须先取得 [G2 验收](../developer/runtime-integration/motion/acceptance.md)真实证据，并在同一批部署中验证 Backend、Runtime、Renderer、CLI 的版本与能力一致；G1 已关闭，不再重复列为开放阻断。
- 指定状态截图在 G2 关闭前保持关闭；临时时间轴截图不得更新页面默认截图；旧 v1 页面、旧 Worker 与旧 Runtime 遇到新请求必须明确失败，不能丢字段执行。
- 继续维护已开放能力的用户文档与支持矩阵；Firefox/WebKit、移动端和未验证编码不得对外宣称。

**下一步**：按 [G2 遗留清单](../developer/runtime-integration/motion/g2-followups.md) 补齐联合创作、生产镜像、混版/回退与长稳证据，再单独提交指定状态截图开放变更。

---

## 使用说明

- 以上事项的完整历史记录保留在 [`docs/archive/architecture-2026-09/`](../archive/architecture-2026-09/README.md)。
- 事项闭环后在对应段落注明完成日期、证据位置和结论。
- 新增待验证事项按相同格式追加，不混入已闭环条目。
