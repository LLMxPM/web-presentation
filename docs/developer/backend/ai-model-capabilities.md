# AI 模型能力与推理策略

聊天模型配置把“模型能力”“平台请求预算”和“用户推理策略”分开管理。

## 推理契约

- `reasoning_mode` 使用 `auto / disabled / enabled`：分别表示跟随模型默认、显式关闭、指定平台强度。
- `reasoning_level` 只在 `enabled` 时使用，固定为 `low / medium / high / max`。
- `max` 表示当前模型档案声明的最高可用档，可能映射为供应商原生 `max`、`xhigh` 或 `high`。
- `ultra`、Pro 和多代理编排不是推理强度，不进入该枚举。

`backend/app/ai/model_capabilities.py` 是聊天模型能力档案和四档映射的单一事实源。解析顺序为手工覆盖、精确/模式档案、供应商默认和平台安全默认。未知模型允许使用，但必须返回 `verified=false` 和警告。

当前档案已覆盖 GPT-5.6 Sol/Terra/Luna、Qwen3.8 Max、Kimi K3 和 GLM-5.2。供应商尚未公开完整最大输出或原生档位的模型使用保守值，并保持 `verified=false`。

## 上下文与输出

- `context_window_tokens`：平台允许单次供应商请求使用的最大输入，由用户直接填写；旧数据保持原数值，不做换算。
- 模型档案中的总上下文与最大输出只用于内部校验和输出预算降级，不是模型配置参数。
- 未识别模型默认使用 `200,000` tokens 可用输入，不阻止保存，但返回“未验证”及最低总窗口提示。

新 Run 使用版本化策略 `fixed-context-budget.v2`，所有预算均为绝对值：

```text
request_output_tokens = min(32,768, 已知模型输出硬上限)
runtime_headroom_tokens = 32,768
compression_target_tokens = 16,384
required_model_context_tokens = context_window_tokens + request_output_tokens
compression_trigger_tokens = context_window_tokens - runtime_headroom_tokens
```

例如可用输入为 `200,000` 时，模型至少需要支持 `232,768` 总上下文，历史约达到 `167,232` tokens 后触发本轮结束后的提前压缩。下一次请求前若预计输入超过可用输入窗口，会先强制压缩；摘要和保留后缀仍超限时返回明确的上下文预算错误。

压缩模型调用固定最多输出 `16,384` tokens。长历史按 tokenizer 完整分块，先生成分块摘要再合并，确定性回退也按 token 截断，不再按字符截断原历史。

## 兼容与快照

旧 `thinking_enabled/thinking_effort` 请求在 Schema 层转换为新契约；同一请求不得混用新旧字段。新 Run 同时固化能力档案版本、四档映射、预算策略版本和全部绝对预算，确认恢复与外部任务不重新计算。没有预算策略版本的历史 Run 继续按旧比例快照恢复。

高级 JSON 不得递归覆盖受管推理与预算字段，包括 OpenAI、OpenRouter、Google 的 thinking 设置，以及 `extra_body` 内的输出、上下文预留和压缩预算。
