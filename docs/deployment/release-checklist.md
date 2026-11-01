<!-- 文件功能：从归档治理计划提取的尚未闭环事项接续，记录发布待验证事项与证据状态。 -->
# 发布检查与待验证事项

以下事项从 [部署形态收敛与配置治理工作计划](../archive/architecture-2026-09/plans/deployment-form-and-config-governance-plan-2026-10-02.md) 提取，在计划归档后继续追踪。文档归档不代表验收完成。

2026-10-16 文件鉴权修复新增发布条件，详见[文件存储鉴权规划](../developer/projects/file-storage-auth-cache-plan.md)：

- 默认保持 `PREVIEW_ORIGIN_ISOLATION_ENABLED=true`，配置独立预览主机名的 DNS / TLS，验证 `/runtime/` 与受保护 `/build-artifacts/`；业务 Cookie 不设置父域 Domain，预览域不加入业务 CORS。受信私有部署可显式关闭隔离使用单 IP，不能将其作为隔离验收证据，详见[配置边界](production/env-vars.md#对外访问)。
- 旧字体桶关闭匿名 ACL / policy，保留 Backend 服务身份迁移读取权限；检查历史绝对 public URL，不能通过重新开放旧入口回滚。
- 排空不兼容 Runtime / Renderer 和构建 attempt；新截图使用内容 hash，旧截图 latest 兼容，不宣称历史表已回填。
- 补齐真实 S3 兼容服务、跨副本、浏览器导出与外部客户端矩阵；采集成本与回源指标后再决定 CDN。
- Editor 私有截图、资源图片、主题 Logo 与字体地址统一对齐实际 API 入口，验证工作台使用 `localhost`、Backend 公开基址使用 `127.0.0.1` 时图片仍能带登录态加载；External API 的绝对文件地址保持原契约。

---

## 1. Renderer / Runtime 镜像拉取验证

**状态**：`v0.3.1` 已发布；ACR 匿名 manifest 与本机 digest 拉取通过，Docker Hub Registry 直连拉取待从非故障网络复核。

2026-10-24 查到两个 Registry 的 platform、Lite、Runtime、Renderer `v0.3.1` 相同 digest；本机从 ACR 按 digest 拉取四镜像，OCI revision 均为 `a94ae57`。Docker Hub 公共标签元数据可读，本机 Registry HEAD 经代理返回 EOF，不能记作直接拉取通过。确切 digest 与升级证据见[动画前版本联合验收记录](../archive/developer-work-2026-10/pre-motion-joint-acceptance.md)。检查脚本 `scripts/contracts/check-compose-images.py` 与 npm script `test:contracts:compose-images` 已就绪。

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

**状态**：源码能力已开放并收敛为 schema 4（2026-10-31），同版部署验证待执行。

2026-11-01 补充：升级到 `20261101_0100` 会强制迁移项目和路由放映配置，旧媒体/时间轴模式改为手动、清理旧字段，现行配置和路由继承保留。部署验证需覆盖带旧配置的数据库升级和项目列表读取；旧 artifact/构建快照仍需重新生成，完整规则见[放映契约](../developer/runtime-integration/slideshow/contract.md#api-与版本)。

Backend `capabilities.slideshow` 声明 `schema_version=4`、`advance_modes` 为 `manual`/`timer`/`scene_end`、`single_window_auto_play` 与 `presenter_auto_play` 为 true、`capture_auto_play` 为 false；`/api/system/scene-capabilities` 另行声明任务角色与独立静态呈现。能力布尔值只表示开发支持，真实浏览器与产物结论由 C3 回填。该声明只对应包含 Scene/Deck 与 Presenter v5 的 Runtime。

**发布要求**：

- Backend 与 Runtime 使用同版部署；不得把声明 schema 4 能力的 Backend 与旧 Runtime 执行池组合后对外宣布支持。平台内部服务不保证混版运行，升级时排空旧服务再切换同版服务。
- 已打开的放映窗口保持创建时的不可变快照；回滚应用不重写历史 artifact。旧 schema 3 及更早配置读取时返回稳定 409，需要按当前版本重建，不保证旧版本可以完整编辑新配置。
- 部署后执行真实浏览器三种翻页模式、保持/释放、循环和 CLI 读改写抽查；不存在暂停或定位入口。MCP 不在当前交付范围。证据记入 [WP21](../archive/developer-work-2026-10/slideshow/work-packages/wp21-m1-integration-release.md)与 [C3](../developer/runtime-integration/playback-redesign/work-packages/c3-acceptance-release.md)。

**下一步**：在目标部署拓扑执行同版升级与回滚演练，并记录版本矩阵和实际证据。

---

## 6. CLI 字体与主题发布包对账

**状态**：主仓与 CLI 的真实流程验收已通过，发布安装包仍须按拟发布提交重新构建并核对版本与摘要。

**下一步**：固定两仓提交、CLI/Skill 版本与 OpenAPI 摘要；从最终提交重建安装包，核对包内容和摘要，不复用早期源码快照的包。历史实施和实测证据见[CLI 字体主题归档](../archive/developer-work-2026-10/cli-font-theme/implementation-plan.md)。

---

## 7. 页内动画收敛与集中实机验收

**状态**：旧时间轴实现已按[放映动画收敛规划](../developer/runtime-integration/playback-redesign-proposal.md)整体替换。A1/A2、B0–B5、C1 与 C2 工程已完成（2026-10-31），旧 `core/motion`、`usePageTimeline.v1`、`Asset*.v2`、Presenter v4 与 `media_end`/`timeline_end`/`auto_start` 已从源码、manifest、E2E 与当前文档清零；C3 集中实机验收与全量主门禁均已通过（2026-11-01，候选 `d565d4d`，`test:all` exit 0），GC 判定通过。`compose-images`、Renderer 取消清理专项与独立 ZIP 与本次 motion 改动无关，按既有验收沿用、本轮未重跑；后续改动触及这三处时需单独重验。

首期 WP01–WP12 与 [G1 证据](../developer/runtime-integration/motion/g1-automation-coverage.md)保留为历史实现记录和风险输入，不代表新实现已验收。旧 [G2 清单](../developer/runtime-integration/motion/g2-followups.md)不再是当前执行入口，逐项承接以[收敛工作包清单](../developer/runtime-integration/playback-redesign/work-packages/README.md)为准。指定时刻状态重建与截图已永久放弃；混版矩阵和 B01–B08 模型量化门槛作废，不再等待后续开放。默认 PNG、诊断附图、缩略图和静态导出保留，改用独立静态态。MCP 不列入本轮交付。

**发布要求**：

- A1/A2 已完成现状核对和验收设计；B0–C2 已逐包完成开发测试、契约与生成门禁，未以旧实现的实机验收作为开发前置。
- [C3 集中验收](../developer/runtime-integration/playback-redesign/work-packages/c3-acceptance-release.md)必须覆盖内置助手/Editor/CLI 联合创作、真实 Renderer、静态跨产物一致性、媒体发声与播放许可、多窗口、WebGL、受保护媒体缓冲、取消清理、最终生产裁剪镜像三角色、独立 ZIP 和至少 30 分钟受控长稳；给出 A04 保留堆的修复或接受结论。执行入口为 `tests/e2e/specs/smoke/scene-*.spec.ts`、`protected-media.spec.ts` 与 `tests/e2e/specs/runtime-heavy/scene-joint.spec.ts`。
- 最终候选源码、Backend/Runtime/Renderer 与 CLI 的契约和能力一致；失败回修后重验受影响场景并重新确认镜像/产物身份。全量主门禁与相关专项通过后才可宣布 GC 通过或 G2 关闭。
- 回填用户文档、支持矩阵和证据位置；Firefox/WebKit、移动端、多屏授权及其它未验证环境不作支持承诺。旧 G1/G2 结果不能替代本次新实现验收。

**下一步**：本轮收敛已收口，不再安排重跑。若后续改动触及 Renderer 取消/超时/迟到 PNG、镜像发布或 ZIP 导出，按 C3 卡片单独补验这三项。

---

## 使用说明

- 架构治理事项的历史记录保留在[架构治理归档](../archive/architecture-2026-09/README.md)；CLI 字体主题的实施与验收记录保留在[开发专题归档](../archive/developer-work-2026-10/README.md)。
- 事项闭环后在对应段落注明完成日期、证据位置和结论。
- 新增待验证事项按相同格式追加，不混入已闭环条目。
