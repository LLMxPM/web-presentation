# 进行中的专题工作

本目录集中维护尚有实施、验收或发布收尾事项的计划与工作包。开发者日常接入和现行字段应先读[开发文档入口](../README.md)及对应契约；这里的阶段记录不替代代码、OpenAPI 或稳定指南。

| 专题 | 当前接续事项 |
| :--- | :--- |
| [音频播放联调](./audio/README.md) | 已默认开放；继续记录未覆盖的浏览器、格式和播放生命周期场景，MCP 不在本轮交付范围 |
| [文件鉴权与缓存](./file-storage-auth-cache-plan.md) | 生产存储、真实 S3 和多副本发布验收 |
| [三维资源与渲染](./threejs-resource-implementation-plan.md) | 后续 glTF 阶段与发布环境证据 |
| [CLI 字体与主题](./cli-font-theme/implementation-plan.md) | 功能验收已通过，发布安装包须按最终提交对账 |
| [CLI OAuth](./cli-oauth-implementation-plan.md) | 主仓授权方案待实施；CLI 客户端在独立仓规划 |
| [PPTX 导出升级](./pptx-export-upgrade-plan.md) | 各阶段退出条件与产物验收 |

专题完成后，将稳定契约和操作说明留在相应开发文档，将计划、工作包及验收记录移到[开发过程归档](../../archive/developer-work-2026-10/README.md)，并修复仓内链接。

页内动画与播放收敛的未合入工作继续由 `feature/motion` 分支跟踪；当前 `dev` 目录不复制该分支的过程文件。待功能合入时，仅把稳定契约和开发入口带入现行文档。
