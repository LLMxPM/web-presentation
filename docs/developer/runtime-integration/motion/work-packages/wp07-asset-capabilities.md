# WP07 资产摘要与能力契约

状态：待实施。主责：Backend / 契约。前置：[WP02](./wp02-contracts-plan-compiler.md)。

## 输入与落点

扩展现有 model3d 分析 DTO、model3d_glb_service、资源详情与 External 能力自省；具体字段见 [创作契约](../authoring-contract.md)，不新增第二份资源或动作目录。

## 交付

- 有界解析动作时长、签名、通道与支持状态；检查采样器数据、插值、目标范围、有限值、规模与接受策略，不只统计 animation 数量。
- 为旧资源提供受限批次的分析升级与失败摘要，查询列表不触发同步大文件解码；未分析不得宣称可用动作。
- 动作引用与当前 file_hash、分析策略和实际加载结果复核；兼容资源替换更新截图身份，不兼容引用明确报错，不读取历史副本兜底。
- 为 timeline、track_types、capture_snapshot、advance_modes 增加能力词汇，默认关闭；沿用 audio/narration 的既有门禁，不用 timeline.enabled 绕过原能力。
- 更新 DTO、OpenAPI、生成 Editor 类型和共享正反例。保持资源稳定 name、权限、归档/引用及受保护 HEAD/Range 规则。
- 明确编排本身不新增资产依赖来源：资源仍来自实际 Asset* 组件的 name；动态 name 继续遵守 build_extra_assets_json 规则。

## 验证与通过条件

Backend 单元/API/契约覆盖 A05、A14，包含纹理变更但动作不变、索引处动作变更、非法采样器、过大轨道与未知分析版本。旧资源详情仍可读，未分析和不支持可区分。

运行 HTTP DTO codegen 与生成漂移检查，验证能力关闭时写入明确失败且客户端不会降级丢字段。

## 交接

向 WP06/WP08/WP09/WP11 提供真实动作摘要和能力结构，开放动作由 WP12 的 G2 决定。

## 实施记录

- 代码版本、分析策略与升级范围：待回填。
- 实际命令、通过/失败数量与正反例：待回填。
- 未覆盖项：待回填。
