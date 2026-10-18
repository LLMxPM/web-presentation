/**
 * 文件功能：验证音频共享 fixture 的阶段能力、资源格式与跨语言映射样例保持自洽。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

interface AudioFixture {
  schema_version: number
  resource: { extensions: Record<string, string[]> }
  capabilities: Record<'m0' | 'm1' | 'm2', string[]>
  defaults: {
    api: Record<string, unknown>
    runtime: RuntimeAudioConfig
  }
  settings_cases: ContractCase[]
  cue_cases: ContractCase[]
  asset_audio_cases: ContractCase[]
  runtime_cases: Array<{
    name: string
    volume: Record<string, number>
    cues: Array<{ key: string; asset_name: string; gain_percent: number }>
    expected: RuntimeAudioConfig
  }>
}

interface ContractCase {
  name: string
  valid: boolean
  error?: string
}

interface RuntimeAudioConfig {
  volume: { master: number; narration: number; effects: number }
  cues: Record<string, { assetName: string; gain: number }>
}

const fixture = JSON.parse(
  readFileSync(resolve(process.cwd(), 'tests/fixtures/audio-contract-cases.json'), 'utf-8'),
) as AudioFixture

/** 按 Backend 契约把 fixture 的 snake_case 输入映射为 Runtime 配置。 */
function buildRuntimeCase(testCase: AudioFixture['runtime_cases'][number]): RuntimeAudioConfig {
  const volume = testCase.volume
  const cues = Object.fromEntries(
    [...testCase.cues]
      .sort((left, right) => left.key.localeCompare(right.key))
      .map(cue => [cue.key, { assetName: cue.asset_name, gain: cue.gain_percent / 100 }]),
  )
  return {
    volume: {
      master: volume.master_volume_percent / 100,
      narration: volume.narration_volume_percent / 100,
      effects: volume.effects_volume_percent / 100,
    },
    cues,
  }
}

describe('音频跨模块共享契约', () => {
  it('冻结 v1 格式和推荐资源类型', () => {
    expect(fixture.schema_version).toBe(1)
    expect(fixture.resource.extensions).toEqual({
      '.mp3': ['audio/mpeg'],
      '.m4a': ['audio/mp4', 'audio/x-m4a'],
      '.aac': ['audio/aac'],
      '.ogg': ['audio/ogg'],
      '.wav': ['audio/wav', 'audio/x-wav'],
    })
  })

  it('里程碑能力只递增且 M0 不提前开放旁白或 cue', () => {
    expect(fixture.capabilities.m0).toEqual(['audio_assets'])
    expect(fixture.capabilities.m1).toEqual(['audio_assets', 'page_narration'])
    expect(fixture.capabilities.m2).toEqual(['audio_assets', 'page_narration', 'audio_cues'])
    expect(new Set(fixture.capabilities.m1)).toEqual(new Set([...fixture.capabilities.m0, 'page_narration']))
    expect(new Set(fixture.capabilities.m2)).toEqual(new Set([...fixture.capabilities.m1, 'audio_cues']))
  })

  it('所有反例都有明确错误且名称在分组内唯一', () => {
    for (const group of [fixture.settings_cases, fixture.cue_cases, fixture.asset_audio_cases]) {
      expect(new Set(group.map(item => item.name)).size).toBe(group.length)
      for (const testCase of group.filter(item => !item.valid)) {
        expect(testCase.error).toBeTruthy()
      }
    }
  })

  it.each(fixture.runtime_cases)('$name 映射为确定性 camelCase Runtime 配置', (testCase) => {
    expect(buildRuntimeCase(testCase)).toEqual(testCase.expected)
  })

  it('默认 API 设置映射到默认 Runtime 设置', () => {
    expect(buildRuntimeCase({
      name: 'defaults',
      volume: {
        master_volume_percent: fixture.defaults.api.master_volume_percent as number,
        narration_volume_percent: fixture.defaults.api.narration_volume_percent as number,
        effects_volume_percent: fixture.defaults.api.effects_volume_percent as number,
      },
      cues: [],
      expected: fixture.defaults.runtime,
    })).toEqual(fixture.defaults.runtime)
  })
})
