# CLI 字体与主题配置工作包执行清单

状态：WP01–WP08 已有实现，WP09 待验收。公共契约和范围以[实施规划](../implementation-plan.md)为准；审查后的实际验证与缺项见[修复记录](../review-fixes.md)，单元/API 检查不等于真实联合验收。

## 执行规则

- 每包对应可独立评审的提交或 PR；跨仓包分别记录版本，不用主仓提交代表 CLI 已完成。
- 状态按“待实施 → 实施中 → 待验收 → 完成”更新。完成必须回填实际测试与未运行项。
- 主仓详细卡片在本目录；CLI 详细卡片在同级 CLI 仓 `docs/font-theme/work-packages/`。
- 开始实现前复核当前源码与契约，保留无关改动；不因领取工作包自动启动服务、重置数据或创建子任务。
- 公共 DTO、operation/capability、生成物由各交付包在自己的最终变更上同步；后合入的包重新生成，不能覆盖前包结果。

## 工作包

| 编号 | 内容与详细卡片 | 主责 | 前置 | 状态 |
| --- | --- | --- | --- | --- |
| WP01 | [契约、样例与兼容边界](./wp01-contract.md) | 主仓 | 无 | 完成 |
| WP02 | [主题写入语义与引用校验](./wp02-theme-semantics.md) | 主仓 | WP01 | 完成 |
| WP03 | [字体服务事务与查询](./wp03-font-service.md) | 主仓 | WP01 | 完成 |
| WP04 | [字体 External API 与能力发现](./wp04-external-fonts.md) | 主仓 | WP01、WP03 | 完成 |
| WP05 | [主题 External 配置一致性](./wp05-external-themes.md) | 主仓 | WP01、WP02 | 完成 |
| WP06 | [CLI 字体与字体族命令](https://github.com/LLMxPM/web-presentation-cli/blob/feature/cli-font-theme/docs/font-theme/work-packages/wp06-font-commands.md) | CLI | WP01、WP04 | 完成 |
| WP07 | [CLI 主题配置与输出](https://github.com/LLMxPM/web-presentation-cli/blob/feature/cli-font-theme/docs/font-theme/work-packages/wp07-theme-commands.md) | CLI | WP01、WP05 | 完成 |
| WP08 | [Skill 与安装包交付](https://github.com/LLMxPM/web-presentation-cli/blob/feature/cli-font-theme/docs/font-theme/work-packages/wp08-skill-distribution.md) | CLI | WP06、WP07 | 完成 |
| WP09 | [联合验收与交付](./wp09-integration.md) | 两仓 | WP02–WP08 | 待验收 |

## 执行顺序与出口

1. WP01 冻结输入，达到 M0。（已完成）
2. WP02 → WP05；WP03 → WP04；两条链均完成达到 M1。（已完成）
3. WP04 → WP06，WP05 → WP07，随后 WP08；CLI 命令与安装包完成达到 M2。（已完成）
4. WP09 当前版本的真实 CLI、PostgreSQL、字体加载/截图和独立构建已通过，见[真实验收记录](../live-validation-2026-10-20.md)。旧平台版本兼容和最终提交固定尚待补齐，完成后达到原规划的 M2 交付出口。

## 每包记录格式

| 项目 | 回填内容 |
| --- | --- |
| 状态/日期 | 实施中、待验收或完成及日期 |
| 代码版本 | 主责仓库完整 commit；跨仓依赖对应 commit/OpenAPI 摘要 |
| 修改摘要 | 最终实现与契约变更，说明偏离计划的原因 |
| 已运行 | 实际命令、结果、必要证据路径 |
| 未运行/跳过 | 原因、实际影响和后续负责包 |
| 遗留项 | 是否影响本包完成与阶段出口 |
