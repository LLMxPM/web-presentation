// 文件功能：WP01 自包含 GLB 解析、独立骨骼实例采样及实际 WebGL 绘制实验。
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { clone } from 'three/addons/utils/SkeletonUtils.js'

/** 根据真实索引选动作；名称重复不影响选择，无动作、无效目标及索引越界必须拒绝。 */
export async function loadModel(url, canvas) {
  const bytes = await (await fetch(url)).arrayBuffer()
  const jsonLength = new DataView(bytes).getUint32(12, true)
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(bytes, 20, jsonLength)))
  for (const animation of json.animations ?? []) for (const channel of animation.channels) {
    if (!json.nodes[channel.target.node]) throw new Error('CLIP_TARGET_MISSING')
  }
  const gltf = await new GLTFLoader().parseAsync(bytes, '')
  if (!gltf.animations.length) throw new Error('CLIP_NOT_FOUND')
  const scene = new THREE.Scene()
  const instances = [clone(gltf.scene), clone(gltf.scene)]
  instances.forEach((instance, i) => { instance.position.x = i ? 1.2 : -1.2; scene.add(instance) })
  const mixers = instances.map(instance => new THREE.AnimationMixer(instance))
  mixers.forEach(mixer => { const action = mixer.clipAction(gltf.animations[0]); action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; action.play() })
  const camera = new THREE.PerspectiveCamera(45, 2, 0.1, 100)
  camera.position.set(0, 1, 7); camera.lookAt(0, 0.5, 0)
  scene.add(new THREE.AmbientLight(0xffffff, 3))
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true })
  renderer.setClearColor(0x182335)
  renderer.setSize(400, 200, false); renderer.setPixelRatio(1)
  /** 每次重置动作再按绝对时间求姿态，避免 LoopOnce 完成后的 paused 状态污染反向定位。 */
  function sample(ms) {
    mixers.forEach((mixer, i) => {
      const action = mixer.clipAction(gltf.animations[0])
      action.reset().play(); mixer.setTime(Math.min(2, Math.max(0, (ms + i * 500) / 1000)))
    })
    renderer.render(scene, camera)
  }
  sample(0)
  return {
    sample,
    visiblePixels() {
      const probe = document.createElement('canvas'); probe.width = 400; probe.height = 200
      const context = probe.getContext('2d'); context.drawImage(canvas, 0, 0)
      const data = context.getImageData(0, 0, 400, 200).data
      let count = 0
      for (let i = 0; i < data.length; i += 4) if (data[i + 2] > 100) count++
      return count
    },
    state: () => instances.map(instance => instance.getObjectByName('joint').quaternion.toArray().map(value => +value.toFixed(6))),
    isolated: instances[0].getObjectByName('triangle').skeleton !== instances[1].getObjectByName('triangle').skeleton,
    clipCount: gltf.animations.length,
    device: () => {
      const context = renderer.getContext(), extension = context.getExtension('WEBGL_debug_renderer_info')
      return { triangles: renderer.info.render.triangles, renderer: extension ? context.getParameter(extension.UNMASKED_RENDERER_WEBGL) : context.getParameter(context.RENDERER), threeRevision: THREE.REVISION }
    },
    dispose() {
      mixers.forEach((mixer, i) => { mixer.stopAllAction(); mixer.uncacheRoot(instances[i]) })
      gltf.scene.traverse(object => { object.geometry?.dispose(); object.material?.dispose() })
      renderer.dispose(); renderer.forceContextLoss()
    },
  }
}
