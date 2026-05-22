---
description: 快速运行后端和前端测试
---

# 快速测试

// turbo-all

## 后端测试

1. 运行后端 pytest 测试：

```bash
cd c:\code\web-presentation\backend
uv run pytest tests/ -v --tb=short
```

## 前端类型检查

2. 运行前端 TypeScript 类型检查：

```bash
cd c:\code\web-presentation\editor
pnpm run build
```
