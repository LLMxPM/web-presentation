/** 文件功能：演示自建 Canvas 有限任务如何用真实 RAF 完成、响应宿主冻结并在离页释放。 */
import type { SceneTask } from '@runtime-kit/public/composables/motion/usePageScene.v1'

/** 每次 Scene 创建独立任务；准备与静态挂载均不获取 Canvas 上下文或启动 RAF。 */
export function createCanvasParticles(canvas: HTMLCanvasElement, poster: SVGElement): SceneTask {
  let active = false, suspended = false, frame = 0, elapsed = 0, last: number | null = null
  let finish: (() => void) | undefined
  let draw: ((timestamp: number) => void) | undefined

  return {
    id: 'canvas', role: 'blocking', afterTrack: 'stroke', offsetMs: 100,
    run(context) {
      const painter = canvas.getContext('2d')
      if (!painter) throw new Error('Canvas 2D 上下文不可用。')
      const original = poster.style.visibility
      active = true
      poster.style.visibility = 'hidden'
      context.onCleanup(() => {
        active = false
        cancelAnimationFrame(frame)
        painter.clearRect(0, 0, canvas.width, canvas.height)
        poster.style.visibility = original
        finish?.()
      })
      return new Promise<void>(resolve => {
        finish = resolve
        /** 有效经过时间只在连续帧累加；冻结恢复丢弃后台墙钟差，不补跑。 */
        draw = timestamp => {
          if (!active || suspended || context.signal.aborted) return
          elapsed += last === null ? 0 : Math.max(0, timestamp - last)
          last = timestamp
          painter.clearRect(0, 0, canvas.width, canvas.height)
          for (let index = 0; index < 18; index += 1) {
            const progress = Math.min(elapsed / 1600, 1)
            const x = 180 + Math.cos(index * 2.4) * (24 + progress * 120)
            const y = 75 + Math.sin(index * 2.4) * (10 + progress * 48)
            painter.fillStyle = index % 2 ? '#38bdf8' : '#818cf8'
            painter.beginPath()
            painter.arc(x, y, 2 + index % 3, 0, Math.PI * 2)
            painter.fill()
          }
          if (elapsed >= 1600) { active = false; resolve(); return }
          frame = requestAnimationFrame(draw!)
        }
        frame = requestAnimationFrame(draw)
      })
    },
    setSuspended(value) {
      suspended = value
      last = null
      cancelAnimationFrame(frame)
      if (!value && active && draw) frame = requestAnimationFrame(draw)
    },
  }
}
