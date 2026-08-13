/**
 * 文件功能：验证 Models.dev 推理选项格式兼容和协议能力交集。
 */
import { describe, expect, it } from 'vitest'

import {
  availableReasoningModes,
  canDisableReasoning,
  protocolReasoningControls,
  reasoningBudgetLimits,
  reasoningControls,
  reasoningEfforts,
} from './reasoning-controls'

describe('reasoning controls', () => {
  it('解析 Models.dev 当前的选项对象数组', () => {
    const raw = [
      { type: 'toggle' },
      { type: 'effort', values: ['none', 'low', 'medium', 'high'] },
      { type: 'budget_tokens', min: 1024, max: 81920 },
    ]

    expect([...reasoningControls(raw)]).toEqual(['toggle', 'effort', 'budget_tokens'])
    expect(reasoningEfforts(raw)).toEqual(['none', 'low', 'medium', 'high'])
    expect(reasoningBudgetLimits(raw)).toEqual({ min: 1024, max: 81920 })
  })

  it('兼容同步后的规范结构与旧缓存结构', () => {
    expect(reasoningEfforts({ types: ['effort'], effort: ['low', 'high'] })).toEqual(['low', 'high'])
    expect(reasoningEfforts({ options: [{ type: 'effort', values: ['low', 'xhigh'] }] })).toEqual(['low', 'xhigh'])
  })

  it('仅在模型与协议共同支持时允许关闭', () => {
    expect(canDisableReasoning([{ type: 'effort', values: ['low', 'high'] }], 'google_chat')).toBe(false)
    expect(canDisableReasoning([{ type: 'effort', values: ['none', 'high'] }], 'openai_chat')).toBe(true)
    expect(canDisableReasoning([{ type: 'toggle' }], 'openai_compatible_chat')).toBe(false)
    expect([...protocolReasoningControls('openai_compatible_chat')]).toEqual(['effort'])
  })

  it('固定协议与通用兼容协议都严格按模型公布的 effort 开放模式', () => {
    const effort = [{ type: 'effort', values: ['none', 'low', 'medium', 'high'] }]

    expect(availableReasoningModes(true, effort, 'openai_chat')).toEqual(['auto', 'disabled', 'effort'])
    expect(availableReasoningModes(true, effort, 'openai_compatible_chat')).toEqual(['auto', 'disabled', 'effort'])
    expect(availableReasoningModes(false, effort, 'openai_chat')).toEqual(['auto'])
  })
})
