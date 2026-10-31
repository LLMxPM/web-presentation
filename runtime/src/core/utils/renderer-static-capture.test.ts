// @vitest-environment jsdom
/** 文件功能：直接执行 Renderer 的捕获脚本，验证画布路由与 Runtime 静态探针的跨端接线。 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, expect, it, vi } from 'vitest'

const source = readFileSync(resolve(process.cwd(), '../renderer/wp_renderer/engine/static_media.py'), 'utf-8')
const script = source.match(/_STATIC_CAPTURE_SCRIPT = r"""([\s\S]*?)"""/)![1]
const capture = new Function(`return (${script})`)() as (input: { timeoutMs: number; expectedRoute: string }) => Promise<{ ok: boolean; layerIssue: string; issues: string[] }>

afterEach(() => {
  document.body.innerHTML = ''
  delete window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__
  vi.restoreAllMocks()
})

/** 真实 DOM 上只替代几何，不需要浏览器布局或截图。 */
function layer() {
  const root = document.createElement('section')
  root.className = 'runtime-page-print-source'
  root.dataset.runtimeRoutePath = '/cover'
  root.getBoundingClientRect = () => ({ width: 1920, height: 1080 }) as DOMRect
  document.body.append(root)
  return root
}

it('PNG 在同一目标层调用共享静态探针，不等待文档动画', async () => {
  const root = layer()
  const probe = vi.fn().mockResolvedValue({ ok: true })
  window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__ = probe
  expect(await capture({ timeoutMs: 300, expectedRoute: '/cover' })).toMatchObject({ ok: true })
  expect(probe).toHaveBeenCalledWith({ root, timeoutMs: 300, staticMedia: true, includeAnimations: false })
})

it('资源失败保留探针原因，不能输出成功或内容不支持', async () => {
  layer()
  window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__ = vi.fn().mockResolvedValue({ ok: false, failed: [{ type: 'video', message: '视频海报加载失败。' }], pending: [] })
  expect(await capture({ timeoutMs: 300, expectedRoute: '/cover' })).toMatchObject({ ok: false, issues: ['视频海报加载失败。'] })
})

it('缺失探针时明确拒绝；重复页面层或路由不符不得继续准备', async () => {
  layer()
  expect(await capture({ timeoutMs: 300, expectedRoute: '/cover' })).toMatchObject({ ok: false, issues: ['Runtime 缺少静态资源就绪探针。'] })
  const probe = vi.fn()
  window.__EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__ = probe
  expect((await capture({ timeoutMs: 300, expectedRoute: '/wrong' })).layerIssue).toContain('路由不一致')
  layer()
  expect((await capture({ timeoutMs: 300, expectedRoute: '/cover' })).layerIssue).toContain('实际 2 个')
  expect(probe).not.toHaveBeenCalled()
})
