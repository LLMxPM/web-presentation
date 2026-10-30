/** 文件功能：验证模型可见性、尺寸与 WebGL 状态的独立所有权和监听释放，不模拟真实上下文恢复成功。 */
import { afterEach, expect, it, vi } from 'vitest'
import { createModelWebglLifecycle } from './webgl-lifecycle'

afterEach(() => { Reflect.deleteProperty(document, 'hidden') })

it('尺寸和可见性不能解除丢失状态，恢复仍交给首帧证明且卸载后不再响应', () => {
  const pause = vi.fn(), lost = vi.fn(), restored = vi.fn(), requestRender = vi.fn()
  const lifecycle = createModelWebglLifecycle({ pause, lost, restored, requestRender }), canvas = document.createElement('canvas')
  try {
    lifecycle.bind(canvas)
    const event = new Event('webglcontextlost', { cancelable: true })
    canvas.dispatchEvent(event); expect(event.defaultPrevented).toBe(true); expect(lost).toHaveBeenCalledOnce()
    lifecycle.setSized(true); lifecycle.setVisible(true); document.dispatchEvent(new Event('visibilitychange'))
    expect(pause).toHaveBeenLastCalledWith(true)
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    canvas.dispatchEvent(new Event('webglcontextrestored'))
    expect(restored).toHaveBeenCalledOnce(); expect(pause).toHaveBeenLastCalledWith(true)
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    document.dispatchEvent(new Event('visibilitychange')); expect(pause).toHaveBeenLastCalledWith(false)
    lifecycle.setSized(false); lifecycle.setVisible(true); expect(pause).toHaveBeenLastCalledWith(true)
  } finally { lifecycle.dispose() }
  const count = pause.mock.calls.length
  canvas.dispatchEvent(new Event('webglcontextrestored')); document.dispatchEvent(new Event('visibilitychange'))
  expect(pause).toHaveBeenCalledTimes(count)
})
