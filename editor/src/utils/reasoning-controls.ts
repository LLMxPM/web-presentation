/**
 * 文件功能：解析 Models.dev 推理选项，并计算模型元数据与固定协议转换器的能力交集。
 */

/** 兼容当前选项对象数组、同步后的规范结构和旧缓存结构。 */
export function reasoningOptionRecords(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) return raw.filter(isOptionRecord)
  if (!raw || typeof raw !== 'object') return []
  const record = raw as Record<string, unknown>
  if (typeof record.type === 'string') return [record]
  if (Array.isArray(record.options) && record.options.some(isOptionRecord)) return record.options.filter(isOptionRecord)
  return []
}

/** 提取模型声明的 toggle、effort 和 budget_tokens 控制类型。 */
export function reasoningControls(raw: unknown): Set<string> {
  const controls = new Set(reasoningOptionRecords(raw).map(item => String(item.type ?? '')).filter(Boolean))
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return controls
  const record = raw as Record<string, unknown>
  if (Array.isArray(record.types)) record.types.forEach(item => controls.add(String(item)))
  if (record.effort || record.efforts || record.levels) controls.add('effort')
  if (record.budget_tokens) controls.add('budget_tokens')
  return controls
}

/** 提取目录公布的 effort 枚举，包含 none 以便判断是否能够关闭。 */
export function reasoningEfforts(raw: unknown): string[] {
  const values: unknown[] = []
  for (const record of reasoningOptionRecords(raw)) {
    if (record.type === 'effort' && Array.isArray(record.values)) values.push(...record.values)
  }
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const record = raw as Record<string, unknown>
    const legacy = record.effort ?? record.efforts ?? record.levels
    if (Array.isArray(legacy)) values.push(...legacy)
    else if (legacy && typeof legacy === 'object') values.push(...Object.keys(legacy))
    if (Array.isArray(record.options) && record.options.every(item => typeof item === 'string')) values.push(...record.options)
  }
  return [...new Set(values.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())).map(item => item.trim()))]
}

/** 提取目录公布的推理 token 预算上下界。 */
export function reasoningBudgetLimits(raw: unknown): { min?: number; max?: number } {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    const record = reasoningOptionRecords(raw).find(item => item.type === 'budget_tokens')
    return positiveLimits(record)
  }
  const normalized = raw as Record<string, unknown>
  if (normalized.budget_tokens && typeof normalized.budget_tokens === 'object') {
    return positiveLimits(normalized.budget_tokens as Record<string, unknown>)
  }
  return positiveLimits(reasoningOptionRecords(raw).find(item => item.type === 'budget_tokens'))
}

/** 返回当前固定协议转换器真正实现的推理控制能力。 */
export function protocolReasoningControls(protocol: string): Set<string> {
  const controls: Record<string, string[]> = {
    openai_chat: ['toggle', 'effort'],
    openai_compatible_chat: ['effort'],
    openrouter_chat: ['toggle', 'effort'],
    google_chat: ['effort'],
    alibaba_openai_compatible: ['toggle', 'budget_tokens'],
    deepseek_openai_compatible: ['toggle', 'effort'],
    xiaomi_openai_compatible: ['toggle'],
    ollama_openai_compatible: ['toggle', 'effort'],
  }
  return new Set(controls[protocol] ?? [])
}

/** 判断模型声明与固定协议是否共同支持明确关闭推理。 */
export function canDisableReasoning(raw: unknown, protocol: string): boolean {
  const modelControls = reasoningControls(raw)
  const protocolControls = protocolReasoningControls(protocol)
  return modelControls.has('toggle') && protocolControls.has('toggle')
    || protocolControls.has('effort') && reasoningEfforts(raw).includes('none')
}

/** 计算一次 Run 可选的推理模式，auto 永远作为安全回退。 */
export function availableReasoningModes(
  supportsReasoning: boolean,
  raw: unknown,
  protocol: string,
): Array<'auto' | 'disabled' | 'effort' | 'budget_tokens'> {
  const modes: Array<'auto' | 'disabled' | 'effort' | 'budget_tokens'> = ['auto']
  if (!supportsReasoning) return modes
  const modelControls = reasoningControls(raw)
  const protocolControls = protocolReasoningControls(protocol)
  if (canDisableReasoning(raw, protocol)) modes.push('disabled')
  if (modelControls.has('effort') && protocolControls.has('effort') && reasoningEfforts(raw).some(value => value !== 'none')) modes.push('effort')
  if (modelControls.has('budget_tokens') && protocolControls.has('budget_tokens')) modes.push('budget_tokens')
  return modes
}

/** 缩小 unknown 的目录选项对象类型。 */
function isOptionRecord(item: unknown): item is Record<string, unknown> {
  return Boolean(item) && typeof item === 'object' && !Array.isArray(item)
}

/** 只接受正整数预算边界，忽略目录中的无效扩展值。 */
function positiveLimits(record: Record<string, unknown> | undefined): { min?: number; max?: number } {
  const result: { min?: number; max?: number } = {}
  if (Number.isInteger(record?.min) && Number(record?.min) > 0) result.min = Number(record?.min)
  if (Number.isInteger(record?.max) && Number(record?.max) > 0) result.max = Number(record?.max)
  return result
}
