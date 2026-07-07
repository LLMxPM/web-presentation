# Editor 测试

Editor 测试入口由根仓脚本统一承接。

## 常用命令

```powershell
pnpm run test:editor
pnpm run test:editor:check
pnpm run test:editor:gate
```

## 命令语义

- `test:editor`：执行 Editor Vitest。
- `test:editor:check`：执行 Editor 类型检查。
- `test:editor:gate`：执行 `check + test`，用于前端质量门禁。

## 补测范围

新增 API 调用、状态管理、AI 侧边栏交互、工具确认、预览 iframe 状态和构建入口时，应补充对应单元测试或组件测试。跨模块行为变化时，还要补充契约测试或 E2E smoke。
