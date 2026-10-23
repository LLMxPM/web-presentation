/**
 * 文件功能：在真实 Runtime 浏览器中验证时间轴 PNG/PDF/PPTX 捕获静音，以及导出取消与主播放状态隔离。
 */
import { readFileSync } from 'node:fs'
import { inflateRawSync } from 'node:zlib'

import type { APIRequestContext, BrowserContext, FrameLocator, Page } from '@playwright/test'
import { expect, test } from '../../fixtures/test-data'
import { countPixels, decodePngPixels } from '../../helpers/png-pixels'
import { longWavDataUri } from '../../helpers/motion-media'

interface RuntimeCaptureObservation {
  kind: 'media-play' | 'capture-snapshot'
  captureMode?: boolean
  execution?: string | null
  muted?: boolean
  paused?: boolean
  request?: unknown
  receipt?: { status?: string; timelineId?: string; sampledTimeMs?: number }
  media?: Array<{ muted: boolean; paused: boolean; currentTime: number }>
}

/** 为全部 Runtime 文档安装媒体与捕获桥探针，只经 Playwright binding 回传最小观察值。 */
async function installCaptureObserver(context: BrowserContext) {
  const observations: Array<RuntimeCaptureObservation & { framePath: string }> = []
  await context.exposeBinding('__a15Observe', ({ frame }: { frame: { url(): string } }, value: RuntimeCaptureObservation) => {
    observations.push({ ...value, framePath: new URL(frame.url()).pathname })
  })
  await context.addInitScript(() => {
    const notify = (value: Record<string, unknown>) => {
      const observer = (window as unknown as { __a15Observe?: (value: unknown) => Promise<void> }).__a15Observe
      if (observer) void observer(value).catch(() => undefined)
    }
    const originalPlay = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function playWithA15Observation() {
      const result = originalPlay.call(this)
      notify({
        kind: 'media-play',
        captureMode: new URLSearchParams(location.search).get('runtimeCapture') === '1' || location.hash.includes('runtimeCapture=1'),
        execution: document.querySelector<HTMLElement>('[data-runtime-execution]')?.dataset.runtimeExecution ?? null,
        muted: this.muted,
        paused: this.paused,
      })
      return result
    }

    let applyMotionSnapshot: ((request?: unknown) => Promise<RuntimeCaptureObservation['receipt']>) | undefined
    Object.defineProperty(window, '__RUNTIME_APPLY_MOTION_SNAPSHOT__', {
      configurable: true,
      get: () => applyMotionSnapshot,
      set: handler => {
        if (typeof handler !== 'function') {
          applyMotionSnapshot = undefined
          return
        }
        applyMotionSnapshot = async request => {
          const receipt = await handler(request)
          notify({
            kind: 'capture-snapshot',
            captureMode: new URLSearchParams(location.search).get('runtimeCapture') === '1' || location.hash.includes('runtimeCapture=1'),
            execution: document.querySelector<HTMLElement>('[data-runtime-execution]')?.dataset.runtimeExecution ?? null,
            request,
            receipt,
            media: Array.from(document.querySelectorAll<HTMLMediaElement>('audio, video')).map(media => ({
              muted: media.muted,
              paused: media.paused,
              currentTime: media.currentTime,
            })),
          })
          return receipt
        }
      },
    })
  })
  return observations
}

/** 构造有声音频与可区分海报姿态的时间轴页面。 */
function buildA15Page(): string {
  // 一次性 30s 音频覆盖两次导出与取消窗口，避免用重复片段干扰导出隔离判断。
  const audio = longWavDataUri(30)
  return `<template>
  <main ref="root" class="a15-page">
    <h1 class="a15-title">A15 导出姿态</h1>
    <audio class="a15-audio" :src="audioSource" preload="auto" @play="markPlayed" @volumechange="syncMuted" />
    <span class="a15-sentinel" :class="{ 'is-muted': audioMuted, 'is-playing': audioPlayed }" aria-hidden="true"></span>
    <button class="a15-start" type="button" @click="startTimeline">启动主时间轴</button>
  </main>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
const audioSource = '${audio}'
const audioMuted = ref(false)
const audioPlayed = ref(false)
const timeline = usePageTimeline({
  root,
  bindings: { title: '.a15-title' },
  muted: false,
  applyPoster: true,
  definition: {
    schemaVersion: 1,
    timelineId: 'a15-export-isolation',
    poster: { atMs: 5000 },
    tracks: [
      { type: 'dom', id: 'title', target: 'title', from: { opacity: 0, x: 0 }, to: { opacity: 1, x: 300 }, durationMs: 10000 },
      { type: 'audio', id: 'voice', asset: 'voice', selector: '.a15-audio', outMs: 30000 },
    ],
  },
})
;(window as Window & { __A15_TIMELINE?: typeof timeline }).__A15_TIMELINE = timeline
onMounted(() => {
  if (root.value) {
    ;(root.value as HTMLElement & { __A15_TIMELINE?: typeof timeline }).__A15_TIMELINE = timeline
  }
})
function markPlayed() { audioPlayed.value = true }
function syncMuted(event: Event) { audioMuted.value = (event.currentTarget as HTMLAudioElement).muted }
async function startTimeline() { await timeline.play() }
</script>
<style scoped>
.a15-page { width: 100%; height: 100%; position: relative; display: grid; place-items: center; overflow: hidden; background: #fff; }
.a15-title { color: #2563eb; font-size: 64px; }
.a15-audio { display: none; }
.a15-sentinel { position: absolute; left: 16px; top: 16px; width: 36px; height: 36px; background: #64748b; }
.a15-sentinel.is-muted { background: #00e676; }
.a15-sentinel.is-playing { background: #ff1744; }
.a15-start { position: absolute; right: 16px; top: 16px; }
</style>`
}

/** 读取主文档时间轴与真实媒体状态，供导出前后对照。 */
async function readMainState(runtime: FrameLocator) {
  return runtime.locator('.page-content-wrapper .a15-title').evaluate((element: HTMLElement) => {
    const pageRoot = element.closest('.a15-page') as (HTMLElement & {
      __A15_TIMELINE?: { state: { value: Record<string, unknown> | null }; error?: { value?: { code?: string } | null } }
    }) | null
    const timeline = pageRoot?.__A15_TIMELINE
      ?? (element.ownerDocument.defaultView as Window & {
        __A15_TIMELINE?: { state: { value: Record<string, unknown> | null }; error?: { value?: { code?: string } | null } }
      }).__A15_TIMELINE
    const audio = element.closest('.page-content-wrapper')?.querySelector<HTMLAudioElement>('.a15-audio')
    const state = timeline?.state.value
    return {
      intent: state?.intent,
      phase: state?.phase,
      positionMs: state?.positionMs,
      errorCode: timeline?.error?.value?.code ?? null,
      audioMuted: audio?.muted,
      audioPaused: audio?.paused,
      route: element.ownerDocument.querySelector<HTMLElement>('[data-runtime-route-path]')?.dataset.runtimeRoutePath,
    }
  })
}

/** 等待远程 Renderer 截图任务完成并返回真实 PNG。 */
async function captureDefaultPng(api: APIRequestContext, pageId: number): Promise<Buffer> {
  const created = await api.post(`/api/pages/${pageId}/screenshot-jobs`, { data: {} })
  expect(created.ok(), await created.text()).toBeTruthy()
  const job = await created.json() as { id: number }
  let terminal: { status: string; error_code: string | null } | null = null
  await expect(async () => {
    const response = await api.get(`/api/pages/screenshot-jobs/${job.id}`)
    expect(response.ok()).toBeTruthy()
    terminal = await response.json()
    expect(terminal!.status, terminal!.error_code ?? '').toBe('succeeded')
  }).toPass({ timeout: 120_000, intervals: [1000, 2000] })
  const content = await api.get(`/api/pages/${pageId}/screenshot-jobs/${job.id}/content`)
  expect(content.ok(), await content.text()).toBeTruthy()
  return Buffer.from(await content.body())
}

interface PixelSummary {
  width: number
  height: number
  green: number
  red: number
  blue: number
  blueCentroidX: number | null
}

/** 统计哨兵绿/播放红/标题蓝像素及其归一化横向重心。 */
function summarizePixels(
  width: number,
  height: number,
  channels: number,
  pixels: Uint8Array | Uint8ClampedArray,
): PixelSummary {
  let green = 0
  let red = 0
  let blue = 0
  let blueX = 0
  for (let offset = 0; offset < pixels.length; offset += channels) {
    const r = pixels[offset]
    const g = pixels[offset + 1]
    const b = pixels[offset + 2]
    if (g > 190 && r < 60 && b > 80 && b < 180) green += 1
    if (r > 220 && g < 60 && b < 100) red += 1
    if (b > 180 && r < 120 && g < 160) {
      blue += 1
      blueX += ((offset / channels) % width)
    }
  }
  return {
    width,
    height,
    green,
    red,
    blue,
    blueCentroidX: blue > 0 ? blueX / blue / width : null,
  }
}

/** 从截图 PDF 中提取唯一的 DCTDecode JPEG 图像。 */
function extractPdfJpeg(pdf: Buffer): Buffer {
  const imageMarker = pdf.indexOf(Buffer.from('/Subtype /Image'))
  const streamStart = imageMarker >= 0 ? pdf.indexOf(Buffer.from('stream'), imageMarker) : -1
  if (streamStart < 0) throw new Error('PDF 未包含图像 XObject')
  let dataStart = streamStart + 'stream'.length
  while (pdf[dataStart] === 0x0d || pdf[dataStart] === 0x0a) dataStart += 1
  const streamEnd = pdf.indexOf(Buffer.from('endstream'), dataStart)
  const soi = pdf.indexOf(Buffer.from([0xff, 0xd8]), dataStart)
  const eoi = pdf.lastIndexOf(Buffer.from([0xff, 0xd9]), streamEnd) + 2
  if (soi < 0 || eoi <= soi) throw new Error('PDF 图像不是完整 JPEG')
  return pdf.subarray(soi, eoi)
}

/** 在浏览器内解码 JPEG 并统计像素，避免为 E2E 引入原生图像依赖。 */
async function summarizeJpeg(page: Page, jpeg: Buffer): Promise<PixelSummary> {
  return page.evaluate(async base64 => {
    const bytes = Uint8Array.from(atob(base64), char => char.charCodeAt(0))
    const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/jpeg' }))
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const context = canvas.getContext('2d')
    if (!context) throw new Error('无法创建 JPEG 解码画布')
    context.drawImage(bitmap, 0, 0)
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height)
    let green = 0
    let red = 0
    let blue = 0
    let blueX = 0
    for (let offset = 0; offset < data.length; offset += 4) {
      const r = data[offset]
      const g = data[offset + 1]
      const b = data[offset + 2]
      if (g > 190 && r < 60 && b > 80 && b < 180) green += 1
      if (r > 220 && g < 60 && b < 100) red += 1
      if (b > 180 && r < 120 && g < 160) {
        blue += 1
        blueX += (offset / 4) % canvas.width
      }
    }
    return {
      width: canvas.width,
      height: canvas.height,
      green,
      red,
      blue,
      blueCentroidX: blue > 0 ? blueX / blue / canvas.width : null,
    }
  }, jpeg.toString('base64'))
}

/** 解压 PPTX 中的指定 ZIP 条目；只支持 deflate/store，足以覆盖导出包。 */
function extractZipText(zip: Buffer, name: string): string {
  const eocd = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]))
  if (eocd < 0) throw new Error('PPTX 缺少 ZIP 目录')
  let offset = zip.readUInt32LE(eocd + 16)
  while (zip.readUInt32LE(offset) === 0x02014b50) {
    const method = zip.readUInt16LE(offset + 10)
    const compressedSize = zip.readUInt32LE(offset + 20)
    const nameLength = zip.readUInt16LE(offset + 28)
    const extraLength = zip.readUInt16LE(offset + 30)
    const commentLength = zip.readUInt16LE(offset + 32)
    const localOffset = zip.readUInt32LE(offset + 42)
    const entryName = zip.subarray(offset + 46, offset + 46 + nameLength).toString('utf8')
    if (entryName === name) {
      const localNameLength = zip.readUInt16LE(localOffset + 26)
      const localExtraLength = zip.readUInt16LE(localOffset + 28)
      const dataStart = localOffset + 30 + localNameLength + localExtraLength
      const data = zip.subarray(dataStart, dataStart + compressedSize)
      return (method === 8 ? inflateRawSync(data) : data).toString('utf8')
    }
    offset += 46 + nameLength + extraLength + commentLength
  }
  throw new Error(`PPTX 缺少条目 ${name}`)
}

/** 新建静态后续路由，以形成真实的长时「导出所有页面」取消窗口。 */
async function addStaticPages(api: APIRequestContext, workspaceId: number, projectId: number, homePageId: number) {
  const pageIds: number[] = []
  const routes = [{ route_type: 'page', route: 'home', order: 0, hidden: false, page_id: homePageId }]
  for (let index = 1; index <= 5; index += 1) {
    const blocks = Array.from({ length: 240 }, (_, block) => `<p>取消导出静态页 ${index} 内容 ${block}</p>`).join('')
    const response = await api.post('/api/pages', {
      data: {
        workspace_id: workspaceId,
        project_id: projectId,
        title: `A15 静态页 ${index}`,
        file_type: 'vue',
        page_content: `<template><main class="a15-static-page"><h1>A15 静态页 ${index}</h1>${blocks}</main></template><style scoped>.a15-static-page{width:100%;height:100%;overflow:hidden}</style>`,
      },
    })
    expect(response.ok(), await response.text()).toBeTruthy()
    const page = await response.json() as { id: number }
    pageIds.push(page.id)
    routes.push({ route_type: 'page', route: `extra-${index}`, order: index, hidden: false, page_id: page.id })
  }
  const routeResponse = await api.put(`/api/projects/${projectId}/routes`, {
    data: { routes },
  })
  return { pageIds, routeResponse }
}

test('PNG/PDF/PPTX 静态捕获应用海报并静音，完成与取消都隔离主时间轴', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(360_000)
  const api = context.request
  const observers = await installCaptureObserver(context)
  const pageUpdate = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: buildA15Page() },
  })
  expect(pageUpdate.ok(), await pageUpdate.text()).toBeTruthy()
  const { pageIds, routeResponse } = await addStaticPages(
    api,
    visualEditSandbox.workspaceId,
    visualEditSandbox.projectId,
    visualEditSandbox.pageId,
  )
  try {
    expect(routeResponse.ok(), await routeResponse.text()).toBeTruthy()
    const png = await captureDefaultPng(api, visualEditSandbox.pageId)
    const decoded = decodePngPixels(png)
    const pngSummary = summarizePixels(decoded.width, decoded.height, decoded.channels, decoded.pixels)
    expect(pngSummary.green, '远程 PNG 应显示捕获时静音标记').toBeGreaterThan(500)
    expect(pngSummary.red, '远程 PNG 捕获页不得启动音频').toBe(0)
    expect(pngSummary.blue, '远程 PNG 应包含海报姿态标题').toBeGreaterThan(500)
    expect(pngSummary.blueCentroidX).not.toBeNull()
    await testInfo.attach('a15-default-poster.png', { body: png, contentType: 'image/png' })

    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    const artifact = await artifactResponse.json() as { preview_url: string }
    await page.goto(artifact.preview_url)
    const runtime = page.frameLocator('iframe#preview')
    // 预览同时保留导出打印源副本，必须限定在可见画布内操作。
    const title = runtime.locator('.page-content-wrapper .a15-title')
    await expect(title).toBeVisible()
    await runtime.locator('.page-content-wrapper .a15-start').click()
    await expect.poll(async () => (await readMainState(runtime)).intent).toBe('playing')
    await expect.poll(async () => (await readMainState(runtime)).audioPaused).toBe(false)
    await expect.poll(async () => observers.filter(item => item.kind === 'media-play' && !item.captureMode).length)
      .toBeGreaterThan(0)

    /** 完成一次真实浏览器导出，并校验离屏桥回执与主放映快照。 */
    async function exportAndCheck(method: 'pptx-editable' | 'canvas-pdf', label: 'HTML转PPTX' | '截图PDF') {
      const stateBefore = await readMainState(runtime)
      const priorSnapshots = observers.filter(item => item.kind === 'capture-snapshot').length
      await runtime.locator('.nav-button--export').click()
      const dialog = runtime.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
      await dialog.getByText(label, { exact: true }).click()
      const downloadPromise = page.waitForEvent('download', { timeout: 120_000 })
      await dialog.getByRole('button', { name: '开始导出' }).click()
      const download = await downloadPromise
      const file = readFileSync((await download.path()) as string)
      if (method === 'pptx-editable') {
        expect(download.suggestedFilename()).toMatch(/\.pptx$/)
        expect(file.subarray(0, 4)).toEqual(Buffer.from([0x50, 0x4b, 0x03, 0x04]))
        const slide = extractZipText(file, 'ppt/slides/slide1.xml')
        expect(slide).toContain('<a:t>A15 导出姿态</a:t>')
        // 海报 5000ms 处 power2.out 进度为 0.875，PPTX 内部文本必须保留该姿态透明度。
        const titleAlpha = Number(/<a:srgbClr val="2563EB"><a:alpha val="(\d+)"\/>/.exec(slide)?.[1] ?? 0)
        expect(titleAlpha).toBeGreaterThan(80000)
        expect(titleAlpha).toBeLessThan(95000)
      } else {
        expect(download.suggestedFilename()).toMatch(/\.pdf$/)
        expect(file.subarray(0, 5).toString('ascii')).toBe('%PDF-')
        const pdfSummary = await summarizeJpeg(page, extractPdfJpeg(file))
        expect(pdfSummary.width).toBe(3840)
        expect(pdfSummary.height).toBe(2160)
        expect(pdfSummary.green, 'PDF 内嵌图像应显示捕获时静音标记').toBeGreaterThan(500)
        expect(pdfSummary.red, 'PDF 内嵌图像不得启动音频').toBe(0)
        expect(pdfSummary.blue, 'PDF 内嵌图像应包含海报姿态标题').toBeGreaterThan(500)
        expect(pdfSummary.blueCentroidX).not.toBeNull()
        expect(Math.abs((pdfSummary.blueCentroidX as number) - (pngSummary.blueCentroidX as number)))
          .toBeLessThan(0.01)
      }
      expect(file.length).toBeGreaterThan(4096)
      await expect.poll(() => observers.filter(item => item.kind === 'capture-snapshot').length, { timeout: 30_000 })
        .toBeGreaterThan(priorSnapshots)
      const snapshots = observers.filter(item => item.kind === 'capture-snapshot').slice(priorSnapshots)
      expect(snapshots.length).toBeGreaterThan(0)
      expect(snapshots.some(item => item.captureMode && item.execution === 'capture' && item.receipt?.status === 'applied'
        && item.receipt.timelineId === 'a15-export-isolation' && item.receipt.sampledTimeMs === 5000
        && item.media?.some(media => media.muted && media.paused))).toBe(true)
      await dialog.getByRole('button', { name: '关闭', exact: true }).click()
      const stateAfter = await readMainState(runtime)
      expect(stateAfter.intent).toBe('playing')
      expect(['ready', 'buffering']).toContain(stateAfter.phase)
      expect(stateAfter.positionMs).toBeGreaterThan(stateBefore.positionMs as number)
      expect(stateAfter.audioMuted).toBe(false)
      // 导出期间的离屏采样会暂停音频；轮询确认导出结束后主时间轴音频恢复播放。
      await expect.poll(async () => (await readMainState(runtime)).audioPaused).toBe(false)
      expect(stateAfter.route).toBe(stateBefore.route)
    }

    await exportAndCheck('pptx-editable', 'HTML转PPTX')
    await exportAndCheck('canvas-pdf', '截图PDF')

    const stateBeforeCancel = await readMainState(runtime)
    const priorSnapshots = observers.filter(item => item.kind === 'capture-snapshot').length
    await runtime.locator('.nav-button--export').click()
    const dialog = runtime.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
    await dialog.getByText('截图PDF', { exact: true }).click()
    await dialog.getByText('所有页面', { exact: true }).click()
    await dialog.getByRole('button', { name: '开始导出' }).click()
    await expect(dialog.getByRole('button', { name: '取消导出' })).toBeVisible()
    await expect.poll(() => observers.filter(item => item.kind === 'capture-snapshot').length, { timeout: 30_000 })
      .toBeGreaterThan(priorSnapshots)
    await dialog.getByRole('button', { name: '取消导出' }).click()
    await expect(dialog.getByRole('heading', { name: '导出失败' })).toBeVisible()
    await expect(dialog.getByText('用户取消导出')).toBeVisible()
    const stateAfterCancel = await readMainState(runtime)
    expect(stateAfterCancel.intent).toBe('playing')
    expect(['ready', 'buffering']).toContain(stateAfterCancel.phase)
    expect(stateAfterCancel.positionMs).toBeGreaterThan(stateBeforeCancel.positionMs as number)
    expect(stateAfterCancel.audioMuted).toBe(false)
    await expect.poll(async () => (await readMainState(runtime)).audioPaused).toBe(false)
    expect(stateAfterCancel.route).toBe(stateBeforeCancel.route)
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  } finally {
    for (const id of pageIds) {
      await api.patch(`/api/pages/${id}`, { data: { status: 'archived' } }).catch(() => undefined)
    }
  }
})

test('远程 PNG 的指定姿态可读且捕获时音频保持静音', async ({ context, visualEditSandbox }, testInfo) => {
    test.skip(process.env.MOTION_CAPTURE_TEST_OPT_IN !== '1', '远程指定状态 PNG 仅在临时开启 motion_snapshot 能力的 E2E Renderer 上运行')
    test.setTimeout(180_000)
    const api = context.request
    const update = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
      data: { page_content: buildA15Page() },
    })
    expect(update.ok(), await update.text()).toBeTruthy()
    const response = await api.post(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs`, {
      data: { motion_snapshot: { timeline_id: 'a15-export-isolation', at_ms: 6000, visual_mode: 'full' } },
    })
    expect(response.ok(), await response.text()).toBeTruthy()
    const job = await response.json() as { id: number }
    let result: { status: string; error_code: string | null; applied_motion: { status?: string; sampled_time_ms?: number } | null } | null = null
    await expect(async () => {
      const status = await api.get(`/api/pages/screenshot-jobs/${job.id}`)
      expect(status.ok()).toBeTruthy()
      result = await status.json()
      expect(result!.status, result!.error_code ?? '').toBe('succeeded')
    }).toPass({ timeout: 120_000, intervals: [1000, 2000] })
    expect(result!.applied_motion).toMatchObject({ status: 'applied', sampled_time_ms: 6000 })
    const content = await api.get(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs/${job.id}/content`)
    expect(content.ok(), await content.text()).toBeTruthy()
    const png = Buffer.from(await content.body())
    const decoded = decodePngPixels(png)
    expect(countPixels(decoded, (red, green, blue) => green > 190 && red < 60 && blue > 80 && blue < 180)).toBeGreaterThan(500)
    expect(countPixels(decoded, (red, green, blue) => red > 220 && green < 60 && blue < 100)).toBe(0)
    await testInfo.attach('a15-selected-pose.png', { body: png, contentType: 'image/png' })
})
