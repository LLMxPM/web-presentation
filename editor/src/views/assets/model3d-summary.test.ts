/**
 * 文件功能：验证模型动作摘要只展示有界字段并标出未分析/不支持原因。
 */

import { describe, expect, it } from 'vitest'

import { summarizeModelAnimations } from './model3d-summary'

describe('summarizeModelAnimations', () => {
  it('无动画时区分已分析和未分析', () => {
    expect(summarizeModelAnimations([], 2)).toEqual({ analyzed: true, text: '无动画', details: [] })
    expect(summarizeModelAnimations(undefined, 0)).toEqual({ analyzed: false, text: '动画未分析', details: [] })
  })

  it('整理动作名称、时长、签名与不支持原因', () => {
    const overview = summarizeModelAnimations([
      { index: 0, name: 'Walk', duration_ms: 1250, signature: 'abcdef1234567890', supported: true },
      { index: 1, name: null, duration_ms: 2000, supported: false, unsupported_reasons: ['包含 Morph Target'] },
    ], 1)

    expect(overview.text).toBe('#0 Walk、#1')
    expect(overview.details[0]).toMatchObject({
      index: 0,
      label: '#0 Walk',
      durationText: '1.25 秒',
      signature: 'abcdef12',
      supported: true,
      issues: [],
    })
    expect(overview.details[1]).toMatchObject({
      index: 1,
      label: '#1',
      durationText: '2 秒',
      supported: false,
      issues: ['包含 Morph Target'],
    })
  })

  it('分析版本缺失时不宣称动作可执行', () => {
    const overview = summarizeModelAnimations([
      { index: 0, name: 'Idle', duration_ms: 1000, supported: true },
    ], 0)

    expect(overview.details[0].supported).toBe(false)
    expect(overview.details[0].issues).toEqual(['动作分析版本缺失，暂不可执行'])
  })
})
