# 契约测试

根仓契约测试位于 `tests/contracts/`，用于约束跨模块接口以及仓库配置、文档和部署边界。

## 当前范围

- `editor-backend/editor-api-contract.test.ts`：约束 Editor 依赖的 Backend API 基本契约。
- `editor-backend/page-visual-edit-protocol.test.ts`：约束页面可视化编辑协议。
- `runtime-backend/project-config-templates.test.ts`：约束 Backend 和 Runtime 配置模板入口与必要结构。
- `runtime-backend/release-artifact-spec.test.ts`：约束构建产物规格。
- `runtime-backend/runtime-kit-manifest.test.ts`：约束 Runtime Kit manifest 公开能力。
- `e2e-backend/e2e-collection-contract.test.ts`：约束 E2E 测试集合与 Backend 的测试数据入口。
- `repository/`：检查文档链接、部署边界和环境变量覆盖；也可单独运行 `pnpm run test:repository`。

## 何时补充

- Backend API 路径、入参、出参或错误语义变化。
- Runtime Kit manifest 或公开 import path 变化。
- 构建 snapshot、release artifact 或回源协议变化。
- Editor 依赖的工具说明、AI 配置或资源结构变化。

## 运行命令

```powershell
pnpm run test:contracts
```
