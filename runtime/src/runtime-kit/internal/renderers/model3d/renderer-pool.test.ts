/** 文件功能：验证模型渲染器只在卸载后复用，并对空闲 WebGL 上下文设置上限。 */
// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import type { Model3dEngine } from './engine'
import { acquireModelRenderer, drainModelRendererPool, releaseModelRenderer } from './renderer-pool'

let created = 0
let disposed = 0

class FakeRenderer {
  readonly domElement: HTMLCanvasElement
  readonly renderLists = { dispose: () => undefined }

  constructor(options: { canvas: HTMLCanvasElement }) {
    this.domElement = options.canvas
    created += 1
  }

  dispose(): void { disposed += 1 }
  forceContextLoss(): void {}
  resetState(): void {}
  setAnimationLoop(): void {}
}

const engine = { THREE: { WebGLRenderer: FakeRenderer } } as unknown as Model3dEngine

afterEach(() => {
  drainModelRendererPool()
  created = 0
  disposed = 0
})

describe('模型 WebGL 渲染器池', () => {
  it('同时显示的实例独占渲染器，卸载后复用同一 canvas', () => {
    const first = acquireModelRenderer(engine)
    const second = acquireModelRenderer(engine)
    expect(first).not.toBe(second)
    expect(created).toBe(2)

    releaseModelRenderer(first, engine)
    const reused = acquireModelRenderer(engine)
    expect(reused).toBe(first)
    expect(reused.domElement).toBe(first.domElement)
    expect(created).toBe(2)

    releaseModelRenderer(second, engine)
    releaseModelRenderer(reused, engine)
    expect(disposed).toBe(0)
  })

  it('空闲上限为四个，超出的实例立即销毁', () => {
    const renderers = Array.from({ length: 5 }, () => acquireModelRenderer(engine))
    renderers.forEach(renderer => releaseModelRenderer(renderer, engine))
    expect(disposed).toBe(1)
    drainModelRendererPool()
    expect(disposed).toBe(5)
  })
})
