/**
 * 文件功能：定义项目音频快照、默认值与防御性归一化，供 cue 引擎和交互 composable 共用。
 */

export interface RuntimeAudioVolume {
  master: number
  narration: number
  effects: number
}

export interface RuntimeAudioCue {
  assetName: string
  gain: number
}

export interface RuntimeAudioConfig {
  volume: RuntimeAudioVolume
  cues: Record<string, RuntimeAudioCue>
}

export const DEFAULT_RUNTIME_AUDIO_CONFIG: RuntimeAudioConfig = {
  volume: { master: 1, narration: 1, effects: 0.3 },
  cues: {},
}

/** 把任意数值收敛为 0–1 的有限数，非法值使用兜底。 */
function normalizeGain(value: unknown, fallback: number): number {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return Math.min(1, Math.max(0, numeric))
}

/** 防御性解析 artifact 音频快照；缺失或损坏时退回默认静音配置。 */
export function normalizeRuntimeAudioConfig(value: unknown): RuntimeAudioConfig {
  if (!value || typeof value !== 'object') return DEFAULT_RUNTIME_AUDIO_CONFIG
  const source = value as { volume?: unknown; cues?: unknown }
  const rawVolume = source.volume && typeof source.volume === 'object'
    ? source.volume as Record<string, unknown>
    : {}
  const cues: Record<string, RuntimeAudioCue> = {}
  if (source.cues && typeof source.cues === 'object') {
    for (const [key, item] of Object.entries(source.cues as Record<string, unknown>)) {
      if (!item || typeof item !== 'object') continue
      const cue = item as Record<string, unknown>
      const assetName = String(cue.assetName ?? '').trim()
      if (!assetName) continue
      cues[key] = {
        assetName,
        gain: normalizeGain(cue.gain, 1),
      }
    }
  }
  return {
    volume: {
      master: normalizeGain(rawVolume.master, 1),
      narration: normalizeGain(rawVolume.narration, 1),
      effects: normalizeGain(rawVolume.effects, 0.3),
    },
    cues,
  }
}

/** 按 cue key 读取绑定；未绑定时返回 null。 */
export function resolveAudioCue(config: RuntimeAudioConfig, key: string): RuntimeAudioCue | null {
  return config.cues[key] ?? null
}

/** 计算统一 cue 音量：master × effects × binding gain。 */
export function resolveCueVolume(config: RuntimeAudioConfig, cue: RuntimeAudioCue): number {
  return normalizeGain(config.volume.master * config.volume.effects * cue.gain, 0)
}

/** 计算旁白有效音量：master × narration × AssetAudio.volume。 */
export function resolveNarrationVolume(config: RuntimeAudioConfig, componentVolume: number): number {
  return normalizeGain(config.volume.master * config.volume.narration * componentVolume, 0)
}

/** 公开 composable 只接受 interaction.* key；transition 通道只能由 shell 触发。 */
export function isInteractionCueKey(value: string): boolean {
  return value.length <= 80 && /^interaction\.[a-z0-9_-]+(?:\.[a-z0-9_-]+)*$/.test(value)
}
