/**
 * 文件功能：使用共享契约样例验证 Runtime 音频参数默认值、严格校验与静态上下文降级。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  resolveAudioPlaybackOptions,
  validateAssetAudioName,
} from './audio-options'

interface FixtureCase {
  name: string
  valid: boolean
  input: Record<string, unknown>
  expected_controls?: boolean
}

// Vitest 的 jsdom 环境没有 file: 形式的 import.meta.url，按包根目录定位仓根共享样例。
const fixturePath = resolve(process.cwd(), '../tests/fixtures/audio-contract-cases.json')
const fixtures = JSON.parse(readFileSync(fixturePath, 'utf-8')) as { asset_audio_cases: FixtureCase[] }

describe('audio options shared contract', () => {
  it.each(fixtures.asset_audio_cases)('$name', (testCase) => {
    const nameError = validateAssetAudioName(testCase.input.name)
    const result = resolveAudioPlaybackOptions({
      purpose: testCase.input.purpose,
      controls: testCase.input.controls,
      volume: testCase.input.volume,
      playbackRate: testCase.input.playback_rate,
      preload: testCase.input.preload,
      loop: testCase.input.loop,
    })
    const hasError = Boolean(nameError || result.error || Object.prototype.hasOwnProperty.call(testCase.input, 'autoplay'))

    expect(!hasError).toBe(testCase.valid)
    if (testCase.valid && testCase.expected_controls !== undefined) {
      expect(result.controls).toBe(testCase.expected_controls)
    }
  })

  it('静态执行上下文应把任何合法 preload 强制降为 none', () => {
    expect(resolveAudioPlaybackOptions({ preload: 'auto', staticContext: true })).toMatchObject({
      preload: 'none',
      error: '',
    })
  })

  it('非有限数字和字符串数字应返回有界错误', () => {
    expect(resolveAudioPlaybackOptions({ volume: Number.NaN }).error).toContain('有限数字')
    expect(resolveAudioPlaybackOptions({ playbackRate: Number.POSITIVE_INFINITY }).error).toContain('有限数字')
    expect(resolveAudioPlaybackOptions({ volume: '0.8' }).error).toBe('音频 volume 必须是 0 到 1 之间的有限数字。')
  })
})
