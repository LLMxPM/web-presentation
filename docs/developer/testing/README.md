# 测试文档

测试文档说明根仓、Backend、Editor、Runtime、契约测试和 E2E smoke 的入口与适用场景。

## 文档导航

| 文档 | 内容 |
| :--- | :--- |
| [测试治理说明](./strategy.md) | L0-L3 测试分层、目录归属和 CI 策略 |
| [测试命令](./commands.md) | 根仓 `pnpm`、Backend `uv` 和 Runtime 委托命令 |
| [契约测试](./contract-tests.md) | Editor-Backend、Runtime-Backend 和 manifest 契约 |
| [E2E smoke](./e2e-smoke.md) | Playwright smoke、测试数据和报告目录 |

## 选择原则

优先运行与改动范围匹配的最小测试集。涉及跨模块契约、权限、Runtime Kit、预览构建或 AI 工具规格时，必须扩大验证范围。
