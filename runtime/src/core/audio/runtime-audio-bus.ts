/** 文件功能：建立当前窗口唯一 AudioBus，并将动态项目音量和执行策略接入总线。 */
import { watch } from 'vue'
import { audioConfig } from '@/core/utils/config'
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { AudioBus } from './audio-bus'

export const runtimeAudioBus = new AudioBus({ config: () => audioConfig.value, allowed: owner => {
  const policy = getRuntimeExecutionPolicy()
  return policy.allowMediaPlayback && (owner !== 'deck' || (policy.kind === 'presentation' && document.fullscreenElement === document.documentElement))
} })
watch(audioConfig, () => runtimeAudioBus.refresh(), { deep: true })

/** 根窗口显式安装生命周期；freeze 与 visibility 独立，恢复不补播旧 cue 或普通内容。 */
export function installRuntimeAudioBusLifecycle(): () => void {
  let frozen = false
  const visibility = () => runtimeAudioBus.setSuspended(document.hidden || frozen)
  const freeze = () => { frozen = true; visibility() }
  const resume = () => { frozen = false; visibility() }
  const pageShow = (event: PageTransitionEvent) => { if (event.persisted) resume() }
  document.addEventListener('visibilitychange', visibility); document.addEventListener('freeze', freeze); document.addEventListener('resume', resume)
  window.addEventListener('pageshow', pageShow); visibility()
  return () => {
    document.removeEventListener('visibilitychange', visibility); document.removeEventListener('freeze', freeze); document.removeEventListener('resume', resume)
    window.removeEventListener('pageshow', pageShow); runtimeAudioBus.setSuspended(true)
  }
}
