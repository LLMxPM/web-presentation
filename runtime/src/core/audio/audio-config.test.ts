/**
 * 文件功能：验证项目音频快照的防御性归一化与 cue 音量计算。
 */

import { describe, expect, it } from 'vitest'

import {
  DEFAULT_RUNTIME_AUDIO_CONFIG,
  isInteractionCueKey,
  normalizeRuntimeAudioConfig,
  resolveAudioCue,
  resolveCueVolume,
  resolveNarrationVolume,
} from './audio-config'

describe('runtime audio config', () => {
  it('缺失或损坏时退回默认静音配置', () => {
    expect(normalizeRuntimeAudioConfig(undefined)).toEqual(DEFAULT_RUNTIME_AUDIO_CONFIG)
    expect(normalizeRuntimeAudioConfig('bad')).toEqual(DEFAULT_RUNTIME_AUDIO_CONFIG)
    expect(normalizeRuntimeAudioConfig({ volume: 'bad', cues: [] })).toEqual(DEFAULT_RUNTIME_AUDIO_CONFIG)
  })

  it('音量与 gain 收敛到 0–1，非法 gain 使用 1', () => {
    const config = normalizeRuntimeAudioConfig({
      volume: { master: -1, narration: '0.4', effects: 2 },
      cues: {
        confirm: { assetName: ' confirm ', gain: '0.5' },
        loud: { assetName: 'loud', gain: 8 },
        invalid: { assetName: 'invalid', gain: 'bad' },
        empty: { assetName: '   ' },
        broken: 'bad',
      },
    })

    expect(config.volume).toEqual({ master: 0, narration: 0.4, effects: 1 })
    expect(config.cues.confirm).toEqual({ assetName: 'confirm', gain: 0.5 })
    expect(config.cues.loud?.gain).toBe(1)
    expect(config.cues.invalid?.gain).toBe(1)
    expect(config.cues).not.toHaveProperty('empty')
    expect(config.cues).not.toHaveProperty('broken')
  })

  it('按 key 读取绑定并计算 master × effects × gain', () => {
    const config = normalizeRuntimeAudioConfig({
      volume: { master: 0.5, narration: 1, effects: 0.4 },
      cues: { confirm: { assetName: 'confirm', gain: 0.5 } },
    })
    const cue = resolveAudioCue(config, 'confirm')

    expect(cue).not.toBeNull()
    expect(resolveAudioCue(config, 'missing')).toBeNull()
    expect(resolveCueVolume(config, cue!)).toBeCloseTo(0.1)
  })

  it('任一音量为零时 cue 音量为零', () => {
    const config = normalizeRuntimeAudioConfig({
      volume: { master: 0, narration: 1, effects: 1 },
      cues: { confirm: { assetName: 'confirm', gain: 1 } },
    })

    expect(resolveCueVolume(config, config.cues.confirm!)).toBe(0)
  })

  it('旁白有效音量按 master × narration × 组件音量计算', () => {
    const config = normalizeRuntimeAudioConfig({
      volume: { master: 0.5, narration: 0.4, effects: 1 },
    })

    expect(resolveNarrationVolume(config, 0.5)).toBeCloseTo(0.1)
    expect(resolveNarrationVolume(config, 0)).toBe(0)
    expect(resolveNarrationVolume({ ...config, volume: { ...config.volume, master: 0 } }, 1)).toBe(0)
  })

  it('公开 cue key 只接受 interaction.* 的合法分段', () => {
    expect(isInteractionCueKey('interaction.confirm')).toBe(true)
    expect(isInteractionCueKey('interaction.quiz.correct')).toBe(true)
    expect(isInteractionCueKey('transition.forward')).toBe(false)
    expect(isInteractionCueKey('interaction')).toBe(false)
    expect(isInteractionCueKey('interaction.')).toBe(false)
    expect(isInteractionCueKey('Interaction.confirm')).toBe(false)
    expect(isInteractionCueKey(`interaction.${'a'.repeat(80)}`)).toBe(false)
  })
})
