/** 文件功能：使用正式公开入口和真实视频，核验模式采样、暂停重播与实际 GLB 签名。 */
import { createApp, defineComponent, h, ref } from 'vue'
import { usePageTimeline } from '@/runtime-kit/public/composables/motion/usePageTimeline.v1'
import { initializeRuntimeExecution } from '@/core/execution/execution-scope'
import { installCaptureMotionBridge } from '@/core/motion/capture-bridge'
import { parseGlbToResource, loadModel3dEngine } from '@/runtime-kit/internal/renderers/model3d/engine'

initializeRuntimeExecution('?runtimeExecution=presentation')
installCaptureMotionBridge()
const app = createApp(defineComponent({ setup() {
  const root = ref<HTMLElement | null>(null)
  const api = usePageTimeline({ root, bindings: {}, timelineId: 'browser', applyPoster: false,
    define: ctx => ({ plan: ctx.resources().video('demo', { asset: 'demo', selector: '.video', startMs: 400, outMs: 1200 }).build(),
      visual(timeline) { timeline.fromTo('.title', { opacity: 0 }, { opacity: 1, duration: 0.5, ease: 'none' }, 0) } }),
  })
  Object.assign(window, { probe: api })
  return () => h('section', { ref: root }, [h('h1', { class: 'title' }, 'Motion 回归'),
    h('video', { class: 'video', muted: true, preload: 'auto', src: '/fixtures/clock.webm', width: 320 })])
} }))
app.mount('#app')
Object.assign(window, { unmountProbe: () => app.unmount(), async checkModelSignatures() {
  const cases = await (await fetch('/signatures.json')).json()
  const engine = await loadModel3dEngine()
  const result = []
  for (const fixture of cases) {
    const encoded = new TextEncoder().encode(JSON.stringify(fixture.gltf))
    const json = new Uint8Array(Math.ceil(encoded.length / 4) * 4).fill(32); json.set(encoded)
    const raw = Uint8Array.from(atob(fixture.buffer_base64), c => c.charCodeAt(0))
    const bin = new Uint8Array(Math.ceil(raw.length / 4) * 4); bin.set(raw)
    const buffer = new ArrayBuffer(28 + json.length + bin.length), view = new DataView(buffer)
    view.setUint32(0, 0x46546c67, true); view.setUint32(4, 2, true); view.setUint32(8, buffer.byteLength, true)
    view.setUint32(12, json.length, true); view.setUint32(16, 0x4e4f534a, true); new Uint8Array(buffer, 20, json.length).set(json)
    view.setUint32(20 + json.length, bin.length, true); view.setUint32(24 + json.length, 0x004e4942, true)
    new Uint8Array(buffer, 28 + json.length).set(bin)
    const resource = await parseGlbToResource(buffer, engine)
    result.push({ name: fixture.name, expected: fixture.signature, actual: resource.animationSignatures?.[0] })
    resource.dispose()
  }
  return result
} })
