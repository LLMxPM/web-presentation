<!-- 文件功能：从归档治理计划提取的尚未闭环事项接续，记录发布待验证事项与证据状态。 -->
# 发布检查与待验证事项

以下事项从 [部署形态收敛与配置治理工作计划](../archive/architecture-2026-09/plans/deployment-form-and-config-governance-plan-2026-10-02.md) 提取，在计划归档后继续追踪。文档归档不代表验收完成。

---

## 1. Renderer 首次发布与匿名拉取验证

**状态**：脚本就绪，镜像尚未发布。

`web-presentation-renderer` 与仓库自构建 `web-runtime-vue` 的推送 job 尚未执行过，两个 registry 中当前不可拉取。检查脚本 `scripts/contracts/check-compose-images.py` 与 npm script `test:contracts:compose-images` 已就绪。

**下一步**：下一次 Release 时执行首次推送，通过 `docker manifest inspect` 验证 Docker Hub 与 ACR 匿名可拉取。

**原始记录**：归档计划 GAT2。

---

## 2. 镜像可拉取性定时 CI

**状态**：检查脚本就绪，定时 CI 未接入。

`check-compose-images.py` 可独立运行检查 compose 模板引用的所有镜像是否可拉取，但尚未接入 GitHub Actions 定时触发。

**下一步**：Renderer 首次发布后，将 `test:contracts:compose-images` 接入 GitHub Actions 定时运行（建议每周）。

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

## 使用说明

- 以上事项的完整历史记录保留在 [`docs/archive/architecture-2026-09/`](../archive/architecture-2026-09/README.md)。
- 事项闭环后在对应段落注明完成日期、证据位置和结论。
- 新增待验证事项按相同格式追加，不混入已闭环条目。
