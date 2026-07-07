# Runtime 接入文档

Runtime 接入文档说明根仓如何依赖 `web-runtime-vue` 子模块，以及页面源码、组件源码、previewSchema、构建产物和配置模板之间的契约。

## 文档导航

| 文档 | 内容 |
| :--- | :--- |
| [子模块协作](./submodule-workflow.md) | Runtime 上游开发、镜像发布和根仓指针更新 |
| [Runtime Kit 契约](./runtime-kit-contract.md) | manifest 命名、版本化 import path 和 Backend 校验 |
| [previewSchema 契约](./preview-schema.md) | 组件预览 schema 的能力边界和校验要求 |
| [构建产物规格](./release-artifact-spec.md) | Runtime 构建产物与 Backend 托管关系 |
| [配置模板边界](./config-templates.md) | Backend 配置模板和 Runtime fixture 配置的边界 |

## 外部文档

Runtime 自身能力、开发方式和内部实现见 [runtime/README.md](../../../runtime/README.md) 以及 `runtime/docs/`。
