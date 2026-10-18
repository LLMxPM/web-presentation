/**
 * 文件功能：在真实放映宿主中创建项目级 cue 引擎，提供交互注入与切页触发入口。
 *
 * 只在允许自动播放的执行上下文创建引擎；窗口化预览、缩略图、捕获和导出
 * 不创建可播放音频元素。静音读取会话状态，跨模式交接保持一致。
 */

import { onBeforeUnmount, onMounted, provide, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { AUDIO_CUE_SERVICE_KEY, type AudioCueService } from '@/core/audio/audio-cue-context'
import { AudioCueEngine, type AudioCueResult } from '@/core/audio/audio-cue-engine'
import { audioConfig } from '@/core/utils/config'
import { getRuntimePreloadedConfig, resolveResourcePath } from '@/core/utils/path'
import { normalizeAssetKey } from '@/core/shared/runtime-preview'
import { getRuntimeSession } from '@/core/router/runtime-session'

export interface RuntimeAudioCues {
  /** 切页方向 cue；仅放映态生效。 */
  playTransitionCue: (direction: 1 | -1) => AudioCueResult
  playInteractionCue: (key: string) => AudioCueResult
}

/**
 * 只把 artifact 已声明的资源逻辑名解析为可播放地址。
 * 关键约束：cue 绑定必须指向当前 manifest 资源；缺映射时 no-op，不回退到相对路径猜测。
 */
function createCueAssetResolver(): (name: string) => string | null {
  const assetMapping = getRuntimePreloadedConfig()?.manifest?.assets || {}
  return (name: string): string | null => {
    const key = normalizeAssetKey(name)
    if (!key || !assetMapping[key]) return null
    return resolveResourcePath(key) || null
  }
}

/**
 * 创建并注入项目 cue 服务。
 * @param active 当前窗口是否实际承担放映发声；普通预览为 false。
 */
export function useAudioCues(active: Ref<boolean>): RuntimeAudioCues {
  const router = useRouter()
  const session = getRuntimeSession(router)
  const policy = useRuntimeExecutionPolicy()
  const allowed = policy.value.allowMediaPlayback && policy.value.allowAutoplay
  const engine = allowed
    ? new AudioCueEngine({
      config: audioConfig.value,
      resolveAssetUrl: createCueAssetResolver(),
      allowPlayback: true,
      isMuted: () => session.audioMuted.value,
    })
    : null

  const noop = (): AudioCueResult => 'unavailable'
  const playInteractionCue = (key: string): AudioCueResult => {
    if (!engine || !active.value) return 'unavailable'
    return engine.playInteraction(key)
  }
  const playTransitionCue = (direction: 1 | -1): AudioCueResult => {
    if (!engine || !active.value) return 'unavailable'
    return engine.playTransition(direction === -1 ? 'transition.backward' : 'transition.forward')
  }

  provide<AudioCueService>(AUDIO_CUE_SERVICE_KEY, { playInteractionCue })

  /** 窗口隐藏、页面冻结时立即停掉短音效；恢复不补播。 */
  const handleVisibility = (): void => {
    if (document.hidden) engine?.suspend()
  }
  const handleFreeze = (): void => {
    engine?.suspend()
  }
  const handlePageShow = (event: PageTransitionEvent): void => {
    if (event.persisted) engine?.suspend()
    else engine?.resume()
  }
  onMounted(() => {
    document.addEventListener('visibilitychange', handleVisibility)
    document.addEventListener('freeze', handleFreeze)
    window.addEventListener('pageshow', handlePageShow)
  })
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', handleVisibility)
    document.removeEventListener('freeze', handleFreeze)
    window.removeEventListener('pageshow', handlePageShow)
    engine?.dispose()
  })

  return {
    playTransitionCue: engine ? playTransitionCue : noop,
    playInteractionCue,
  }
}
