// 文件功能：验证当前发布包的 Three.js 对象变换入口；不加载模型、不渲染，也不把对象变换等同骨骼动作系统。
import { Object3D } from 'three'
import 'animejs/adapters/three'
import { createTimeline } from 'animejs'
import { animate } from 'motion'
import { threeEffect } from 'motion/three'

/** 同题定位到一半，检查位置和角度映射；资源句柄与骨骼 Mixer 仍由 Runtime 负责。 */
export async function probeAdapters() {
  const animeObject = new Object3D(), motionObject = new Object3D()
  const anime = createTimeline({ autoplay: false })
    .add(animeObject, { x: [0, 2], rotateY: [0, 90], duration: 1000, ease: 'linear' }, 0)
    .init()
  anime.seek(500, true)
  animate.addEffect(threeEffect)
  const motion = animate(motionObject, { x: [0, 2], rotateY: [0, 90] }, { duration: 1, ease: 'linear', autoplay: false })
  motion.pause(); motion.time = 0.5
  await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
  const state = {
    anime: { x: animeObject.position.x, rotateYDegrees: animeObject.rotation.y * 180 / Math.PI },
    motionJS: { x: motionObject.position.x, rotateYDegrees: motionObject.rotation.y * 180 / Math.PI },
  }
  anime.revert(); motion.cancel()
  return state
}
