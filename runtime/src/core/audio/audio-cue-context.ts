/**
 * 文件功能：定义 Runtime shell 与页面公开 composable 之间的音频 cue 注入契约。
 */

import { inject, type InjectionKey } from 'vue'

import type { AudioCueResult } from './audio-cue-engine'

export interface AudioCueService {
  /** 播放交互 cue；无 provider、静态上下文或未绑定时返回 no-op。 */
  playInteractionCue: (key: string) => AudioCueResult
}

export const AUDIO_CUE_SERVICE_KEY: InjectionKey<AudioCueService> = Symbol('runtime-audio-cue-service')

/** 读取最近的 cue 服务；没有 provider 时返回稳定 no-op。 */
export function useInjectedAudioCueService(): AudioCueService {
  return inject(AUDIO_CUE_SERVICE_KEY, null) ?? {
    playInteractionCue: () => 'unavailable',
  }
}
