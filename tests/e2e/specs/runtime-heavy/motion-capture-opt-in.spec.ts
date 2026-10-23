/** 文件功能：在临时开启捕获能力的隔离 E2E Backend 上验证指定状态的远程截图链路。 */
import { expect, test } from '../../fixtures/test-data'
import { countPixels, countStrongRedPixels, decodePngPixels } from '../../helpers/png-pixels'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

test.skip(process.env.MOTION_CAPTURE_TEST_OPT_IN !== '1', '仅临时测试入口开启指定状态捕获时运行')

/** 真实 Runtime Kit 时间轴页面，零点标题透明、1800ms 标题可读。 */
function motionSource(): string {
  return `<template><main ref="root" class="capture-page"><h1 class="capture-title">远程帧验证</h1><span class="capture-marker">.</span></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({ root, bindings: { title: '.capture-title', marker: '.capture-marker' }, applyPoster: true,
  definition: { schemaVersion: 1, timelineId: 'capture-e2e', poster: { atMs: 1800 },
    tracks: [{ type: 'dom', id: 'title', target: 'title', preset: 'fade', durationMs: 1800 },
      { type: 'dom', id: 'marker', target: 'marker', from: { opacity: 0 }, to: { opacity: 0 },
        startMs: 1800, durationMs: 1, label: 'readable' }] } })
</script>
<style scoped>.capture-page{width:100%;height:100%;display:grid;place-items:center;background:#fff}.capture-title{font-size:76px;color:#b91c1c}.capture-marker{position:absolute;left:0;top:0;color:#fff}</style>`
}

test('远程 Renderer 指定零点与海报帧，临时结果不提升默认截图', async ({ context, visualEditSandbox }, testInfo) => {
  test.setTimeout(240_000)
  const api = context.request
  const pageId = visualEditSandbox.pageId
  const updated = await api.patch(`/api/pages/${pageId}`, { data: { page_content: motionSource() } })
  expect(updated.ok(), await updated.text()).toBeTruthy()

  /** 等待真实 Worker 终态并读取受保护 PNG，断言回执与所请求时刻一致。 */
  async function capture(selector?: { at_ms?: number; at_label?: string; offset_ms?: number }) {
    const payload = selector === undefined ? {} : {
      motion_snapshot: { timeline_id: 'capture-e2e', ...selector, visual_mode: 'full' },
    }
    const response = await api.post(`/api/pages/${pageId}/screenshot-jobs`, { data: payload })
    expect(response.ok(), await response.text()).toBeTruthy()
    const created = await response.json() as { id: number }
    let terminal: { status: string; error_code: string | null; applied_motion: Record<string, unknown> | null } | null = null
    await expect(async () => {
      const statusResponse = await api.get(`/api/pages/screenshot-jobs/${created.id}`)
      expect(statusResponse.ok()).toBeTruthy()
      terminal = await statusResponse.json()
      expect(terminal!.status, terminal!.error_code ?? '').toBe('succeeded')
    }).toPass({ timeout: 120_000, intervals: [1_000, 2_000] })
    const content = await api.get(`/api/pages/${pageId}/screenshot-jobs/${created.id}/content`)
    expect(content.ok(), await content.text()).toBeTruthy()
    const png = Buffer.from(await content.body())
    const decoded = decodePngPixels(png)
    await testInfo.attach(`motion-${selector?.at_label ?? selector?.at_ms ?? 'default'}-${selector?.offset_ms ?? 0}.png`, { body: png, contentType: 'image/png' })
    return { id: created.id, terminal: terminal!, red: countStrongRedPixels(decoded), pixels: decoded.width * decoded.height,
      pixelBytes: Buffer.from(decoded.pixels) }
  }

  const poster = await capture()
  const before = await api.get(`/api/pages/${pageId}`)
  const beforeDetail = await before.json() as { screenshot_url: string }
  expect(beforeDetail.screenshot_url).toBeTruthy()
  const zero = await capture({ at_ms: 0 })
  const late = await capture({ at_ms: 1800 })
  const repeatedLate = await capture({ at_ms: 1800 })
  const labeled = await capture({ at_label: 'readable' })
  const offset = await capture({ at_label: 'readable', offset_ms: -300 })
  expect(zero.id).not.toBe(late.id)
  expect(repeatedLate.id).not.toBe(late.id)
  expect(repeatedLate.terminal.applied_motion?.state_digest).toBe(late.terminal.applied_motion?.state_digest)
  expect(repeatedLate.pixelBytes.equals(late.pixelBytes)).toBe(true)
  expect(zero.red / zero.pixels).toBeLessThan(0.0005)
  expect(late.red / late.pixels).toBeGreaterThan(0.001)
  expect(late.terminal.applied_motion).toMatchObject({ status: 'applied', sampled_time_ms: 1800 })
  expect(labeled.terminal.applied_motion).toMatchObject({ status: 'applied', sampled_time_ms: 1800 })
  expect(offset.terminal.applied_motion).toMatchObject({ status: 'applied', sampled_time_ms: 1500 })
  expect(Math.abs(labeled.red - late.red) / late.pixels).toBeLessThan(0.0005)
  expect(offset.red).toBeLessThan(late.red)
  expect(poster.red / poster.pixels).toBeGreaterThan(0.001)
  const after = await api.get(`/api/pages/${pageId}`)
  const afterDetail = await after.json() as { screenshot_url: string }
  expect(afterDetail.screenshot_url).toBe(beforeDetail.screenshot_url)
})

test('远程指定状态截图真实解码受保护视频帧', async ({ context, visualEditSandbox }, testInfo) => {
  test.setTimeout(240_000)
  const api = context.request
  const pageId = visualEditSandbox.pageId
  const name = `motion-capture-video-${randomUUID().slice(0, 8)}`
  const upload = await api.post(`/api/workspaces/${visualEditSandbox.workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${name}.webm`, mimeType: 'video/webm',
        buffer: readFileSync(resolve('runtime/public/video/runtime-video-showcase.webm')) },
      asset_type: 'video',
      tags: '[]',
      name,
    },
  })
  expect(upload.ok(), await upload.text()).toBeTruthy()
  const source = `<template><main ref="root" class="motion-video-capture"><AssetVideo name="${name}" class="motion-video-frame" /></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v2.vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({ root, bindings: {}, applyPoster: true,
  definition: { schemaVersion: 1, timelineId: 'video-capture-e2e', poster: { atMs: 0 },
    tracks: [{ type: 'video', id: 'clip', asset: '${name}', selector: '.motion-video-frame video',
      outMs: 2000, muted: true }] } })
</script>
<style scoped>.motion-video-capture{width:100%;height:100%;display:grid;place-items:center;background:#fff}.motion-video-frame{width:720px;height:400px}</style>`
  const updated = await api.patch(`/api/pages/${pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()

  /** 请求远程 Worker 捕获并归一化像素，供相同与不同时点的比对。 */
  async function capture(atMs: number) {
    const response = await api.post(`/api/pages/${pageId}/screenshot-jobs`, {
      data: { motion_snapshot: { timeline_id: 'video-capture-e2e', at_ms: atMs, visual_mode: 'full' } },
    })
    expect(response.ok(), await response.text()).toBeTruthy()
    const job = await response.json() as { id: number }
    let applied: { status: string; sampled_time_ms: number; state_digest: string } | null = null
    await expect(async () => {
      const status = await api.get(`/api/pages/screenshot-jobs/${job.id}`)
      expect(status.ok()).toBeTruthy()
      const result = await status.json() as { status: string; error_code: string | null; applied_motion: typeof applied }
      expect(result.status, result.error_code ?? '').toBe('succeeded')
      applied = result.applied_motion
    }).toPass({ timeout: 120_000, intervals: [1_000, 2_000] })
    expect(applied).toMatchObject({ status: 'applied', sampled_time_ms: atMs })
    const content = await api.get(`/api/pages/${pageId}/screenshot-jobs/${job.id}/content`)
    expect(content.ok(), await content.text()).toBeTruthy()
    const png = Buffer.from(await content.body())
    await testInfo.attach(`video-${atMs}-${job.id}.png`, { body: png, contentType: 'image/png' })
    return { applied: applied!, decoded: decodePngPixels(png) }
  }

  const zero = await capture(0)
  const later = await capture(900)
  const repeated = await capture(900)
  expect(later.applied.state_digest).toBe(repeated.applied.state_digest)
  expect(later.decoded.width).toBe(zero.decoded.width)
  expect(later.decoded.height).toBe(zero.decoded.height)
  const pixelCount = zero.decoded.width * zero.decoded.height
  const colored = countPixels(later.decoded, (r, g, b) => Math.max(r, g, b) - Math.min(r, g, b) > 30)
  expect(colored / pixelCount).toBeGreaterThan(0.005)
  let changed = 0
  for (let index = 0; index < later.decoded.pixels.length; index += later.decoded.channels) {
    const delta = Math.abs(later.decoded.pixels[index] - zero.decoded.pixels[index])
      + Math.abs(later.decoded.pixels[index + 1] - zero.decoded.pixels[index + 1])
      + Math.abs(later.decoded.pixels[index + 2] - zero.decoded.pixels[index + 2])
    if (delta > 40) changed += 1
  }
  expect(changed / pixelCount).toBeGreaterThan(0.002)
  expect(Buffer.from(later.decoded.pixels).equals(Buffer.from(repeated.decoded.pixels))).toBe(true)
})
