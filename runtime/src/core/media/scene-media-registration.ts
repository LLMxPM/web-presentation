/** 文件功能：显式登记资源组件的媒体用途与寿命，Scene 只认领页面点名的目标，不扫描 DOM。 */
export interface SceneMediaRegistration {
  purpose: 'content' | 'narration' | 'automatic'
  gain: number
  getGain?: () => number
  muted: boolean
  loop: boolean
  signal: AbortSignal
}
const registrations = new WeakMap<HTMLMediaElement, SceneMediaRegistration>()

/** 组件切换源、用途或卸载时必须注销，已保存的 Scene 任务随之失效。 */
export function registerSceneMedia(element: HTMLMediaElement, options: Omit<SceneMediaRegistration, 'signal'>): () => void {
  const controller = new AbortController(), registration = { ...options, signal: controller.signal }
  registrations.set(element, registration)
  return () => { if (registrations.get(element) === registration) registrations.delete(element); controller.abort() }
}

/** 未声明用途的普通 HTML 媒体不能被 Scene 自动接管。 */
export function readSceneMediaRegistration(element: HTMLMediaElement): SceneMediaRegistration | undefined { return registrations.get(element) }
