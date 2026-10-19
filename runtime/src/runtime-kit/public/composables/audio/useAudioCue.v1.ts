/**
 * 文件功能：公开 Runtime Kit v1 语义音效 API，页面只按 cue key 请求播放。
 *
 * 不存在 shell provider、处于静态上下文、没有绑定或会话静音时返回稳定 no-op，
 * 不暴露 URL、资产 ID、Audio 实例或音量绕过入口。
 */

import { isInteractionCueKey } from '@/core/audio/audio-config'
import { useInjectedAudioCueService } from '@/core/audio/audio-cue-context'
import type { AudioCueResult } from '@/core/audio/audio-cue-engine'

export interface UseAudioCueApi {
  /** 请求播放语义 cue；返回值只表达同步可观察状态，不等待音频结束。 */
  playCue: (key: string) => AudioCueResult
}

export function useAudioCue(): UseAudioCueApi {
  const service = useInjectedAudioCueService()
  return {
    playCue: (key: string): AudioCueResult => {
      if (typeof key !== 'string') return 'unavailable'
      const normalized = key.trim()
      // 公开 API 只允许 interaction.*；系统 transition 通道不向页面开放。
      if (!isInteractionCueKey(normalized)) return 'unavailable'
      return service.playInteractionCue(normalized)
    },
  }
}
