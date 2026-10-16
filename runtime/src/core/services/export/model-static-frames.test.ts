// @vitest-environment jsdom

/**
 * 文件用途：验证三维模型静态帧的准备/清理生命周期、幂等保护与缓存分区语义。
 *
 * 覆盖约束：覆盖图与 canvas 隐藏状态可恢复；重复 prepare 不叠加覆盖层且内层 cleanup
 * 不移除外层覆盖层；缓存键包含资源身份、视角、视口尺寸与 DPR；相同资源不同视角不共用。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  MODEL_STATIC_FRAME_HANDLE_KEY,
  MODEL_STATIC_FRAME_IMG_ATTR,
  MODEL_STATIC_FRAME_VERSION,
  findModelStaticFrameImage,
  readModelStaticFrameHandle,
  type ModelStaticFrameHandle,
  type ModelStaticFrameIdentity,
} from '@/core/shared/model-static-frame-contract'

import {
  ModelStaticFrameCache,
  buildModelStaticFrameCacheKey,
  clearDefaultModelStaticFrameCache,
  cleanupModelStaticFrames,
  prepareModelStaticFrames,
} from './model-static-frames'

interface StubModelRoot {
  root: HTMLElement
  canvas: HTMLCanvasElement
  /** 采集次数，验证缓存复用 */
  captures: number
}

/**
 * 构造带采集句柄的模型根节点。
 * @param overrides 身份字段覆盖（用于构造不同视角/视口）
 * @param options.captureResult 传入 null 模拟未就绪；传入 'throw' 模拟采集异常
 */
function createStubModelRoot(
  overrides: Partial<ModelStaticFrameIdentity> = {},
  options: { describeNull?: boolean; captureThrow?: boolean } = {},
): StubModelRoot {
  const host = document.createElement('div')
  host.innerHTML = `
    <div data-runtime-kit-media="v1" data-runtime-kit-media-kind="model3d" style="position: relative; width: 320px; height: 200px;">
      <div class="model-viewer__surface"><canvas width="640" height="400"></canvas></div>
    </div>
  `
  const root = host.firstElementChild as HTMLElement
  const canvas = root.querySelector('canvas') as HTMLCanvasElement
  const identity: ModelStaticFrameIdentity = {
    resourceName: 'product',
    resourceSrc: 'https://assets.example.com/hash-product.glb?token=preview',
    viewKey: '{"cameraIndex":0}',
    frameWidth: 640,
    frameHeight: 400,
    ...overrides,
  }
  const stub = { root, canvas, captures: 0 }
  const handle: ModelStaticFrameHandle = {
    describe: () => (options.describeNull ? null : { ...identity }),
    capture: () => {
      stub.captures += 1
      if (options.captureThrow) {
        throw new Error('context lost')
      }
      const dataUrl = `data:image/png;base64,frame-${stub.captures}-${identity.viewKey.length}`
      return { ...identity, dataUrl }
    },
  }
  ;(root as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = handle
  document.body.appendChild(host)
  return stub
}

/**
 * 读取模型根上的覆盖图。
 * @param root 模型根元素
 */
function overlayOf(root: HTMLElement): HTMLImageElement | null {
  return root.querySelector<HTMLImageElement>(`img[${MODEL_STATIC_FRAME_IMG_ATTR}="${MODEL_STATIC_FRAME_VERSION}"]`)
}

afterEach(() => {
  document.body.innerHTML = ''
  clearDefaultModelStaticFrameCache()
})

describe('静态帧准备与清理', () => {
  it('应插入同尺寸覆盖图并隐藏 canvas，cleanup 后无残留且幂等', () => {
    const { root, canvas } = createStubModelRoot()

    const handle = prepareModelStaticFrames(root)

    expect(handle.preparedCount).toBe(1)
    const overlay = overlayOf(root)
    expect(overlay).not.toBeNull()
    expect(overlay?.src.startsWith('data:image/png')).toBe(true)
    expect(overlay?.style.position).toBe('absolute')
    expect(overlay?.style.width).toBe('100%')
    expect(overlay?.style.height).toBe('100%')
    expect(canvas.style.visibility).toBe('hidden')

    handle.cleanup()
    expect(overlayOf(root)).toBeNull()
    expect(canvas.style.visibility).toBe('')
    expect(root.querySelector('canvas')).toBe(canvas)

    // 幂等：重复 cleanup 无副作用
    expect(() => handle.cleanup()).not.toThrow()
    expect(overlayOf(root)).toBeNull()
  })

  it('cleanupModelStaticFrames 应安全接受空句柄', () => {
    expect(() => cleanupModelStaticFrames(null)).not.toThrow()
    expect(() => cleanupModelStaticFrames(undefined)).not.toThrow()
  })

  it('未就绪实例（describe 返回 null）不应插入覆盖图也不应调用 capture', () => {
    const { root } = createStubModelRoot({}, { describeNull: true })

    const handle = prepareModelStaticFrames(root)

    expect(handle.preparedCount).toBe(0)
    expect(overlayOf(root)).toBeNull()
    handle.cleanup()
  })

  it('无采集句柄的模型根应被跳过，不产生覆盖图', () => {
    const host = document.createElement('div')
    host.innerHTML = `
      <div data-runtime-kit-media="v1" data-runtime-kit-media-kind="model3d">
        <canvas width="100" height="100"></canvas>
      </div>
    `
    document.body.appendChild(host)
    const root = host.firstElementChild as HTMLElement

    const handle = prepareModelStaticFrames(root)

    expect(handle.preparedCount).toBe(0)
    expect(overlayOf(root)).toBeNull()
  })

  it('capture 抛异常时应视为未准备，不残留覆盖图', () => {
    const { root, canvas } = createStubModelRoot({}, { captureThrow: true })

    const handle = prepareModelStaticFrames(root)

    expect(handle.preparedCount).toBe(0)
    expect(overlayOf(root)).toBeNull()
    expect(canvas.style.visibility).toBe('')
  })

  it('重复 prepare 应幂等：第二次不叠加覆盖图，内层 cleanup 不移除外层覆盖图', () => {
    const { root, canvas } = createStubModelRoot()

    const outer = prepareModelStaticFrames(root)
    const inner = prepareModelStaticFrames(root)

    expect(outer.preparedCount).toBe(1)
    expect(inner.preparedCount).toBe(0)
    expect(root.querySelectorAll(`img[${MODEL_STATIC_FRAME_IMG_ATTR}]`)).toHaveLength(1)

    // 内层先清理：外层覆盖图与 canvas 隐藏状态必须保留
    inner.cleanup()
    expect(overlayOf(root)).not.toBeNull()
    expect(canvas.style.visibility).toBe('hidden')

    outer.cleanup()
    expect(overlayOf(root)).toBeNull()
    expect(canvas.style.visibility).toBe('')
  })

  it('cleanup 后再次 prepare 应重新创建覆盖图（不残留幂等标记）', () => {
    const { root } = createStubModelRoot()

    prepareModelStaticFrames(root).cleanup()
    const second = prepareModelStaticFrames(root)

    expect(second.preparedCount).toBe(1)
    expect(overlayOf(root)).not.toBeNull()
    second.cleanup()
  })

  it('根节点自身是模型根时应同样准备', () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const { root } = (() => {
      const stub = createStubModelRoot()
      document.body.removeChild(stub.root.parentElement as HTMLElement)
      host.appendChild(stub.root)
      return { root: stub.root }
    })()

    const handle = prepareModelStaticFrames(root)

    expect(handle.preparedCount).toBe(1)
    handle.cleanup()
    expect(overlayOf(root)).toBeNull()
  })

  it('普通页面节点不应被识别为模型根', () => {
    const host = document.createElement('div')
    host.innerHTML = '<section><img src="data:image/png;base64,AAAA" /></section>'
    document.body.appendChild(host)

    const handle = prepareModelStaticFrames(host)

    expect(handle.preparedCount).toBe(0)
  })

  it('cover 层应覆盖多个 canvas 并逐个恢复可见性', () => {
    const { root } = createStubModelRoot()
    const extra = document.createElement('canvas')
    extra.style.visibility = 'collapse'
    root.appendChild(extra)

    const handle = prepareModelStaticFrames(root)

    expect(extra.style.visibility).toBe('hidden')
    handle.cleanup()
    // 恢复原始内联值而不是清空
    expect(extra.style.visibility).toBe('collapse')
  })
})

describe('静态帧缓存分区', () => {
  it('同资源同视角同视口应复用缓存帧，不重新采集', () => {
    const first = createStubModelRoot()
    prepareModelStaticFrames(first.root).cleanup()

    const second = createStubModelRoot()
    const handle = prepareModelStaticFrames(second.root)

    expect(first.captures).toBe(1)
    // 第二次命中缓存，不触发实例采集
    expect(second.captures).toBe(0)
    expect(overlayOf(second.root)).not.toBeNull()
    handle.cleanup()
  })

  it('相同资源不同视角不得共用缓存帧', () => {
    const first = createStubModelRoot()
    prepareModelStaticFrames(first.root).cleanup()

    const second = createStubModelRoot({ viewKey: '{"cameraIndex":1}' })
    prepareModelStaticFrames(second.root).cleanup()

    expect(first.captures).toBe(1)
    expect(second.captures).toBe(1)
  })

  it('相同资源相同视角但视口尺寸或 DPR 不同不得共用', () => {
    const first = createStubModelRoot()
    prepareModelStaticFrames(first.root).cleanup()

    const second = createStubModelRoot({ frameWidth: 1280, frameHeight: 800 })
    prepareModelStaticFrames(second.root).cleanup()

    expect(first.captures).toBe(1)
    expect(second.captures).toBe(1)
  })

  it('资源地址不同（同名不同版本/票据）不得共用', () => {
    const first = createStubModelRoot()
    prepareModelStaticFrames(first.root).cleanup()

    const second = createStubModelRoot({ resourceSrc: 'https://assets.example.com/hash-product-2.glb' })
    prepareModelStaticFrames(second.root).cleanup()

    expect(first.captures).toBe(1)
    expect(second.captures).toBe(1)
  })

  it('任务级缓存传入 clear 后应重新采集', () => {
    const cache = new ModelStaticFrameCache()

    const first = createStubModelRoot()
    prepareModelStaticFrames(first.root, { cache }).cleanup()
    expect(first.captures).toBe(1)

    const second = createStubModelRoot()
    prepareModelStaticFrames(second.root, { cache }).cleanup()
    expect(second.captures).toBe(0)

    cache.clear()
    const third = createStubModelRoot()
    prepareModelStaticFrames(third.root, { cache }).cleanup()
    expect(third.captures).toBe(1)
  })

  it('cache 传 null 时禁用缓存，每次重新采集', () => {
    const first = createStubModelRoot()
    prepareModelStaticFrames(first.root, { cache: null }).cleanup()

    const second = createStubModelRoot()
    prepareModelStaticFrames(second.root, { cache: null }).cleanup()

    expect(first.captures).toBe(1)
    expect(second.captures).toBe(1)
  })

  it('缓存键应拼接资源身份、视角键与帧尺寸', () => {
    const identity: ModelStaticFrameIdentity = {
      resourceName: 'product',
      resourceSrc: 'src.glb',
      viewKey: 'vk',
      frameWidth: 640,
      frameHeight: 400,
    }

    const key = buildModelStaticFrameCacheKey(identity)
    expect(key).toBe(JSON.stringify(['product', 'src.glb', 'vk', 640, 400]))
    expect(buildModelStaticFrameCacheKey({ ...identity, viewKey: 'vk2' })).not.toBe(key)
    expect(buildModelStaticFrameCacheKey({ ...identity, frameWidth: 641 })).not.toBe(key)
    expect(buildModelStaticFrameCacheKey({ ...identity, resourceName: 'other' })).not.toBe(key)
    expect(buildModelStaticFrameCacheKey({ ...identity, resourceSrc: 'other.glb' })).not.toBe(key)
  })

  it('ModelStaticFrameCache 应按容量 LRU 淘汰并支持命中刷新', () => {
    const cache = new ModelStaticFrameCache(2)
    cache.set('a', 'data:image/png;base64,A')
    cache.set('b', 'data:image/png;base64,B')

    // 命中 a 后 a 变为最近使用
    expect(cache.get('a')).toBe('data:image/png;base64,A')
    cache.set('c', 'data:image/png;base64,C')

    expect(cache.size).toBe(2)
    expect(cache.get('a')).not.toBeNull()
    expect(cache.get('b')).toBeNull()
    expect(cache.get('c')).not.toBeNull()
    cache.clear()
    expect(cache.size).toBe(0)
  })

  it('非法容量的缓存应回退默认容量且不抛异常', () => {
    const cache = new ModelStaticFrameCache(Number.NaN)
    for (let index = 0; index < 12; index += 1) {
      cache.set(`k${index}`, `data:image/png;base64,${index}`)
    }
    expect(cache.size).toBeLessThanOrEqual(8)
  })
})

describe('共享契约读取', () => {
  it('readModelStaticFrameHandle 应做鸭子类型校验', () => {
    const element = document.createElement('div')
    expect(readModelStaticFrameHandle(element)).toBeNull()

    ;(element as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = { describe: () => null }
    expect(readModelStaticFrameHandle(element)).toBeNull()

    const handle = { describe: () => null, capture: () => null }
    ;(element as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = handle
    expect(readModelStaticFrameHandle(element)).toBe(handle)
  })

  it('findModelStaticFrameImage 只识别直接子级上的标记图片', () => {
    const host = document.createElement('div')
    const frame = document.createElement('img')
    frame.setAttribute(MODEL_STATIC_FRAME_IMG_ATTR, MODEL_STATIC_FRAME_VERSION)
    const wrapper = document.createElement('div')
    const nested = document.createElement('img')
    nested.setAttribute(MODEL_STATIC_FRAME_IMG_ATTR, MODEL_STATIC_FRAME_VERSION)
    wrapper.appendChild(nested)
    const plain = document.createElement('img')
    host.append(frame, wrapper, plain)

    expect(findModelStaticFrameImage(host)).toBe(frame)
    // wrapper 的直接子级是 nested，按直接子级语义应命中
    expect(findModelStaticFrameImage(wrapper)).toBe(nested)
    expect(findModelStaticFrameImage(plain)).toBeNull()

    // 只在更深的层级带标记时不应命中（避免误用嵌套里的图片）
    const deepOnly = document.createElement('div')
    const shallowWrapper = document.createElement('div')
    shallowWrapper.appendChild(nested.cloneNode())
    deepOnly.appendChild(shallowWrapper)
    expect(findModelStaticFrameImage(deepOnly)).toBeNull()
  })

  it('覆盖图使用目标元素所属文档创建（跨 realm 安全）', () => {
    const foreignDoc = document.implementation.createHTMLDocument('iframe-doc')
    const root = foreignDoc.createElement('div')
    root.setAttribute('data-runtime-kit-media', 'v1')
    root.setAttribute('data-runtime-kit-media-kind', 'model3d')
    const canvas = foreignDoc.createElement('canvas')
    canvas.width = 320
    canvas.height = 200
    root.appendChild(canvas)
    ;(root as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = {
      describe: () => ({
        resourceName: 'foreign',
        resourceSrc: 'foreign.glb',
        viewKey: 'vk',
        frameWidth: 320,
        frameHeight: 200,
      }),
      capture: () => ({
        resourceName: 'foreign',
        resourceSrc: 'foreign.glb',
        viewKey: 'vk',
        frameWidth: 320,
        frameHeight: 200,
        dataUrl: 'data:image/png;base64,foreign',
      }),
    }

    const handle = prepareModelStaticFrames(root)
    const overlay = findModelStaticFrameImage(root)

    expect(handle.preparedCount).toBe(1)
    expect(overlay?.ownerDocument).toBe(foreignDoc)
    handle.cleanup()
    expect(findModelStaticFrameImage(root)).toBeNull()
  })

  it('句柄 describe 抛异常时应按未准备处理且不向上抛出', () => {
    const host = document.createElement('div')
    const root = document.createElement('div')
    root.setAttribute('data-runtime-kit-media', 'v1')
    root.setAttribute('data-runtime-kit-media-kind', 'model3d')
    host.appendChild(root)
    document.body.appendChild(host)
    ;(root as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = {
      describe: () => {
        throw new Error('realm 断开')
      },
      capture: vi.fn(() => null),
    }

    expect(() => prepareModelStaticFrames(root)).not.toThrow()
    expect(prepareModelStaticFrames(root).preparedCount).toBe(0)
  })
})
