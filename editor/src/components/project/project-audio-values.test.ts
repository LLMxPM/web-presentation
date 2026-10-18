/** 文件功能：验证项目音频草稿的创建、校验、API 映射与最终增益计算。 */
import { describe, expect, it } from 'vitest'

import type { ProjectAudioSettings } from '@/types/api'
import {
  calculateCueGainPercent,
  createAudioSettingsDraft,
  formatCueGainPercent,
  isValidInteractionCueKey,
  normalizeAudioSettingsDraft,
  validateAudioSettingsDraft,
} from './project-audio-values'

const settings: ProjectAudioSettings = {
  master_volume_percent: 80,
  narration_volume_percent: 90,
  effects_volume_percent: 25,
  cue_bindings: [
    { key: 'transition.backward', asset_id: 52, gain_percent: 60 },
    { key: 'interaction.quiz.confirm', asset_id: 51, gain_percent: 75 },
    { key: 'transition.forward', asset_id: 53, gain_percent: 100 },
  ],
}

describe('project audio values', () => {
  it('从 API 设置恢复三段音量、切页与交互绑定', () => {
    const draft = createAudioSettingsDraft(settings)

    expect(draft.masterVolume).toBe('80')
    expect(draft.narrationVolume).toBe('90')
    expect(draft.effectsVolume).toBe('25')
    expect(draft.transitionForward).toEqual({ key: 'transition.forward', assetId: '53', gainPercent: '100' })
    expect(draft.transitionBackward).toEqual({ key: 'transition.backward', assetId: '52', gainPercent: '60' })
    expect(draft.interactionCues).toEqual([
      { key: 'interaction.quiz.confirm', assetId: '51', gainPercent: '75' },
    ])
  })

  it('缺失设置时使用默认音量且不绑定 cue', () => {
    const draft = createAudioSettingsDraft(null)

    expect(draft).toMatchObject({
      masterVolume: '100',
      narrationVolume: '100',
      effectsVolume: '30',
      interactionCues: [],
    })
    expect(draft.transitionForward.assetId).toBe('')
    expect(normalizeAudioSettingsDraft(draft)).toEqual({
      master_volume_percent: 100,
      narration_volume_percent: 100,
      effects_volume_percent: 30,
      cue_bindings: [],
    })
  })

  it('提交时只包含已绑定行，并保持切页在前', () => {
    const draft = createAudioSettingsDraft(settings)
    draft.interactionCues.push({ key: 'interaction.blank', assetId: '', gainPercent: '100' })

    expect(normalizeAudioSettingsDraft(draft)).toEqual({
      master_volume_percent: 80,
      narration_volume_percent: 90,
      effects_volume_percent: 25,
      cue_bindings: [
        { key: 'transition.forward', asset_id: 53, gain_percent: 100 },
        { key: 'transition.backward', asset_id: 52, gain_percent: 60 },
        { key: 'interaction.quiz.confirm', asset_id: 51, gain_percent: 75 },
      ],
    })
  })

  it('校验音量、交互 key、重复 key、未选资源与增益', () => {
    const draft = createAudioSettingsDraft(null)
    expect(validateAudioSettingsDraft(draft)).toBeNull()

    draft.masterVolume = '101'
    expect(validateAudioSettingsDraft(draft)).toContain('主音量')
    draft.masterVolume = '100'

    draft.interactionCues.push({ key: 'transition.forward', assetId: '', gainPercent: '100' })
    expect(validateAudioSettingsDraft(draft)).toContain('interaction.confirm')
    draft.interactionCues[0].key = 'interaction.confirm'
    expect(validateAudioSettingsDraft(draft)).toContain('还没有选择音频资源')
    draft.interactionCues[0].assetId = '1'

    draft.interactionCues.push({ key: 'interaction.confirm', assetId: '2', gainPercent: '100' })
    expect(validateAudioSettingsDraft(draft)).toContain('重复')

    draft.interactionCues.pop()
    draft.interactionCues[0].gainPercent = '150'
    expect(validateAudioSettingsDraft(draft)).toContain('绑定增益')
  })

  it('交互 key 只接受 interaction 命名空间', () => {
    expect(isValidInteractionCueKey('interaction.confirm')).toBe(true)
    expect(isValidInteractionCueKey('interaction.quiz.correct')).toBe(true)
    expect(isValidInteractionCueKey('interaction.')).toBe(false)
    expect(isValidInteractionCueKey(' transition.forward')).toBe(false)
    expect(isValidInteractionCueKey('Interaction.Confirm')).toBe(false)
  })

  it('最终增益为主音量 × 音效音量 × 绑定增益', () => {
    expect(calculateCueGainPercent('80', '25', '50')).toBe(10)
    expect(calculateCueGainPercent('100', '30', '100')).toBe(30)
    expect(calculateCueGainPercent('0', '100', '100')).toBe(0)
    expect(calculateCueGainPercent('101', '100', '100')).toBeNull()
    expect(formatCueGainPercent(10)).toBe('10%')
    expect(formatCueGainPercent(12.35)).toBe('12.4%')
    expect(formatCueGainPercent(null)).toBe('待填写')
  })
})
