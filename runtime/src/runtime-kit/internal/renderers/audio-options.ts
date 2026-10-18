/**
 * 文件功能：集中校验并解析 AssetAudio/AudioViewer 的播放参数与静态上下文降级规则。
 */

export type AudioPurpose = 'content' | 'narration'
export type AudioPreload = 'none' | 'metadata' | 'auto'

export interface AudioPlaybackOptionInput {
  purpose?: unknown
  controls?: unknown
  volume?: unknown
  playbackRate?: unknown
  preload?: unknown
  loop?: unknown
  staticContext?: boolean
}

export interface ResolvedAudioPlaybackOptions {
  purpose: AudioPurpose
  controls: boolean
  volume: number
  playbackRate: number
  preload: AudioPreload
  loop: boolean
  error: string
}

const PURPOSES = new Set<AudioPurpose>(['content', 'narration'])
const PRELOAD_VALUES = new Set<AudioPreload>(['none', 'metadata', 'auto'])

/** 校验资源逻辑名，和跨模块契约保持非空、最长 255 字符的边界。 */
export function validateAssetAudioName(value: unknown): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return '音频资源名不能为空。'
  }
  if (value.trim().length > 255) {
    return '音频资源名不能超过 255 个字符。'
  }
  return ''
}

/**
 * 严格解析音频播放参数；错误时返回安全默认值和有界错误文案，不回显不受信输入。
 * @param input 页面传入的原始播放属性
 * @returns 可安全绑定到原生 audio 的参数和错误状态
 */
export function resolveAudioPlaybackOptions(input: AudioPlaybackOptionInput): ResolvedAudioPlaybackOptions {
  const purpose = input.purpose ?? 'content'
  if (!PURPOSES.has(purpose as AudioPurpose)) {
    return invalidOptions('音频 purpose 只允许 content 或 narration。')
  }

  const controls = input.controls ?? purpose === 'content'
  if (typeof controls !== 'boolean') {
    return invalidOptions('音频 controls 必须是布尔值。')
  }

  const volume = input.volume ?? 1
  if (!isFiniteNumberInRange(volume, 0, 1)) {
    return invalidOptions('音频 volume 必须是 0 到 1 之间的有限数字。')
  }

  const playbackRate = input.playbackRate ?? 1
  if (!isFiniteNumberInRange(playbackRate, 0.5, 2)) {
    return invalidOptions('音频 playbackRate 必须是 0.5 到 2 之间的有限数字。')
  }

  const preload = input.preload ?? 'metadata'
  if (!PRELOAD_VALUES.has(preload as AudioPreload)) {
    return invalidOptions('音频 preload 只允许 none、metadata 或 auto。')
  }

  const loop = input.loop ?? false
  if (typeof loop !== 'boolean') {
    return invalidOptions('音频 loop 必须是布尔值。')
  }
  if (purpose === 'narration' && loop) {
    return invalidOptions('页面旁白不允许循环播放。')
  }

  return {
    purpose: purpose as AudioPurpose,
    controls,
    volume: volume as number,
    playbackRate: playbackRate as number,
    preload: input.staticContext ? 'none' : preload as AudioPreload,
    loop,
    error: '',
  }
}

/** 判断值是否是指定闭区间内的有限数字，显式拒绝字符串和布尔值。 */
function isFiniteNumberInRange(value: unknown, minimum: number, maximum: number): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
}

/** 构造不会触发预加载或循环的安全错误结果。 */
function invalidOptions(error: string): ResolvedAudioPlaybackOptions {
  return {
    purpose: 'content',
    controls: false,
    volume: 1,
    playbackRate: 1,
    preload: 'none',
    loop: false,
    error,
  }
}
