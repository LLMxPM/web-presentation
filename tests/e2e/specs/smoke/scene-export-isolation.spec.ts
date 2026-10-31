/**
 * 文件功能：在真实 Runtime 浏览器中验证独立静态 PNG/PDF/PPTX 捕获静音，以及放映、导出与取消互不干扰。
 * 静态姿态由页面显式声明，不来自播放进度；导出使用离屏静态舞台，不推进主画布的 Scene 或媒体。
 */
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { inflateRawSync } from 'node:zlib'

import type { APIRequestContext, BrowserContext, Page } from '@playwright/test'
import { expect, test } from '../../fixtures/test-data'
import { decodePngPixels } from '../../helpers/png-pixels'
import { toneWavBuffer } from '../../helpers/media-wav'

interface RuntimeCaptureObservation {
  kind: 'media-play' | 'static-ready'
  captureMode?: boolean
  execution?: string | null
  muted?: boolean
  paused?: boolean
  receipt?: { status?: string; code?: string }
  media?: Array<{ muted: boolean; paused: boolean; currentTime: number }>
}

/** 为全部 Runtime 文档安装媒体与静态就绪探针，只经 Playwright binding 回传最小观察值。 */
async function installCaptureObserver(context: BrowserContext) {
  const observations: Array<RuntimeCaptureObservation & { framePath: string }> = []
  await context.exposeBinding('__sceneExportObserve', ({ frame }: { frame: { url(): string } }, value: RuntimeCaptureObservation) => {
    observations.push({ ...value, framePath: new URL(frame.url()).pathname })
  })
  await context.addInitScript(() => {
    const notify = (value: Record<string, unknown>) => {
      const observer = (window as unknown as { __sceneExportObserve?: (value: unknown) => Promise<void> }).__sceneExportObserve
      if (observer) void observer(value).catch(() => undefined)
    }
    const originalPlay = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function observedPlay() {
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

    let readyState: { mounted?: boolean; staticPresentation?: RuntimeCaptureObservation['receipt'] } | undefined
    Object.defineProperty(window, '__RENDER_READY__', {
      configurable: true,
      get: () => readyState,
      set: value => {
        readyState = value
        if (!value?.mounted || value.staticPresentation?.status !== 'ready') return
        notify({
          kind: 'static-ready',
          captureMode: new URLSearchParams(location.search).get('runtimeCapture') === '1' || location.hash.includes('runtimeCapture=1'),
          execution: document.querySelector<HTMLElement>('[data-runtime-execution]')?.dataset.runtimeExecution ?? null,
          receipt: value.staticPresentation,
          media: Array.from(document.querySelectorAll<HTMLMediaElement>('audio, video')).map(media => ({
            muted: media.muted,
            paused: media.paused,
            currentTime: media.currentTime,
          })),
        })
      },
    })
  })
  return observations
}

/**
 * 构造带旁白与长序列的 Scene 页面，并声明独立于播放进度的可读静态姿态。
 * 静态态把标题固定在 150px、媒体静音；播放态从 0 走向 300px，两者不可能重合。
 */
function buildSceneExportPage(narrationName: string): string {
  return `<template>
  <main ref="root" class="scene-export-page">
    <h1 class="scene-export-title" :style="isStatic ? { opacity: 1, transform: 'translateX(150px)' } : undefined">导出姿态</h1>
    <AssetAudio :name="narration" purpose="narration" @play="audioPlayed = true" @media-ready="target = $event" @media-unmounted="target = null" />
    <span class="scene-export-sentinel" :class="{ 'is-muted': audioMuted, 'is-playing': audioPlayed }" aria-hidden="true"></span>
  </main>
</template>
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'
import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const narration = '${narrationName}'
const root = ref<HTMLElement | null>(null)
const target = ref<HTMLMediaElement | null>(null)
const audioMuted = ref(false)
const audioPlayed = ref(false)
const { isStatic } = useStaticPresentation({
  root,
  mode: 'poster',
  async prepare() {
    // 静态准备只静音并固化姿态，绝不调用 play 或修改 currentTime。
    const audio = root.value?.querySelector<HTMLAudioElement>('audio')
    if (audio) audio.muted = true
    audioMuted.value = true
    await nextTick()
  },
})
usePageScene({ root, define(scene) {
  scene.visual({ id: 'title', role: 'blocking', define(timeline) {
    timeline.fromTo('.scene-export-title', { opacity: 0, x: 0 }, { opacity: 1, x: 300, duration: 10, ease: 'none' })
  } })
  scene.task(createSceneMediaTask({ id: 'voice', role: 'blocking', target: () => target.value }))
} })
</script>
<style scoped>
.scene-export-page { width: 100%; height: 100%; position: relative; display: grid; place-items: center; overflow: hidden; background: #fff; }
.scene-export-title { color: #2563eb; font-size: 64px; }
.scene-export-sentinel { position: absolute; left: 16px; top: 16px; width: 36px; height: 36px; background: #64748b; }
.scene-export-sentinel.is-muted { background: #00e676; }
.scene-export-sentinel.is-playing { background: #ff1744; }
</style>`
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
  }).toPass({ timeout: 120_000, intervals: [1_000, 2_000] })
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
  return { width, height, green, red, blue, blueCentroidX: blue > 0 ? blueX / blue / width : null }
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
    return { width: canvas.width, height: canvas.height, green, red, blue, blueCentroidX: blue > 0 ? blueX / blue / canvas.width : null }
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
    const blocks = Array.from({ length: 240 }, (_, block) => `<p>导出静态页 ${index} 内容 ${block}</p>`).join('')
    const response = await api.post('/api/pages', {
      data: {
        workspace_id: workspaceId,
        project_id: projectId,
        title: `导出静态页 ${index}`,
        file_type: 'vue',
        page_content: `<template><main class="scene-export-static-page"><h1>导出静态页 ${index}</h1>${blocks}</main></template><style scoped>.scene-export-static-page{width:100%;height:100%;overflow:hidden}</style>`,
      },
    })
    expect(response.ok(), await response.text()).toBeTruthy()
    const created = await response.json() as { id: number }
    pageIds.push(created.id)
    routes.push({ route_type: 'page', route: `extra-${index}`, order: index, hidden: false, page_id: created.id })
  }
  const routeResponse = await api.put(`/api/projects/${projectId}/routes`, { data: { routes } })
  return { pageIds, routeResponse }
}

test('PNG/PDF/PPTX 使用独立静态呈现，放映与导出取消都互不干扰', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(360_000)
  const api = context.request
  const observers = await installCaptureObserver(context)
  // 一次性 30 秒真实旁白覆盖放映、两次导出与取消窗口，避免用重复片段干扰隔离判断。
  const narrationName = `scene-export-voice-${randomUUID().slice(0, 8)}`
  const narration = await api.post(`/api/workspaces/${visualEditSandbox.workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${narrationName}.wav`, mimeType: 'audio/wav', buffer: toneWavBuffer(30) },
      asset_type: 'audio',
      tags: '[]',
      name: narrationName,
    },
  })
  expect(narration.ok(), await narration.text()).toBeTruthy()
  const pageUpdate = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: buildSceneExportPage(narrationName) },
  })
  expect(pageUpdate.ok(), await pageUpdate.text()).toBeTruthy()
  const advance = await api.patch(`/api/projects/${visualEditSandbox.projectId}`, {
    data: { slideshow: {
      transition: { effect: 'none', duration_ms: 0 },
      advance: { mode: 'manual', delay_ms: 5000, completion_delay_ms: 300 },
      loop: false,
    } },
  })
  expect(advance.ok(), await advance.text()).toBeTruthy()
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
    expect(pngSummary.blue, '远程 PNG 应包含独立静态标题').toBeGreaterThan(500)
    expect(pngSummary.blueCentroidX).not.toBeNull()
    await testInfo.attach('scene-static-presentation.png', { body: png, contentType: 'image/png' })

    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    await page.goto((await artifactResponse.json()).preview_url as string)
    const runtime = page.frameLocator('iframe#preview')
    // 预览同时保留导出打印源副本，必须限定在可见画布内操作。
    const canvas = runtime.locator('.page-content-wrapper')
    const title = canvas.locator('.scene-export-title')
    const audio = canvas.locator('audio')
    await expect(title).toBeVisible()
    // 未显式播放时 Scene 不执行：模板保持完整可读，媒体保持暂停。
    await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
    await expect(audio).toHaveJSProperty('paused', true)
    await expect(observers.filter(item => item.kind === 'media-play').length).toBe(0)

    // 进入放映才真实执行 Scene：标题进入长序列，旁白不静音并实际发声。
    await runtime.getByRole('button', { name: '进入放映' }).click()
    await expect(canvas.locator('.scene-export-sentinel')).toHaveClass(/is-playing/, { timeout: 30_000 })
    await expect(audio).toHaveJSProperty('paused', false)
    await expect(audio).toHaveJSProperty('muted', false)
    await expect.poll(() => title.evaluate(element => Number(getComputedStyle(element).opacity))).toBeLessThan(1)
    await expect(observers.some(item => item.kind === 'media-play' && !item.captureMode && item.muted === false)).toBe(true)
    await runtime.getByRole('button', { name: '退出放映' }).click()
    // 停止必须恢复模板初值，导出不继承播放中途或播放结束的姿态。
    await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
    await expect(audio).toHaveJSProperty('paused', true)

    /** 完成一次真实浏览器导出，并校验离屏静态回执与主画布状态。 */
    async function exportAndCheck(method: 'pptx-editable' | 'canvas-pdf', label: 'HTML转PPTX' | '截图PDF') {
      const priorSnapshots = observers.filter(item => item.kind === 'static-ready').length
      const playsBefore = observers.filter(item => item.kind === 'media-play').length
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
        expect(slide).toContain('<a:t>导出姿态</a:t>')
        // 独立静态标题完全可见且停在声明的 150px 姿态，不取播放中途的半透明状态。
        expect(slide).toMatch(/<a:srgbClr val="2563EB"(?:\/>|>)/)
        const titleAlpha = Number(/<a:srgbClr val="2563EB"><a:alpha val="(\d+)"\/>/.exec(slide)?.[1] ?? 100000)
        expect(titleAlpha).toBe(100000)
      } else {
        expect(download.suggestedFilename()).toMatch(/\.pdf$/)
        expect(file.subarray(0, 5).toString('ascii')).toBe('%PDF-')
        const pdfSummary = await summarizeJpeg(page, extractPdfJpeg(file))
        expect(pdfSummary.width).toBe(3840)
        expect(pdfSummary.height).toBe(2160)
        expect(pdfSummary.green, 'PDF 内嵌图像应显示捕获时静音标记').toBeGreaterThan(500)
        expect(pdfSummary.red, 'PDF 内嵌图像不得启动音频').toBe(0)
        expect(pdfSummary.blue, 'PDF 内嵌图像应包含独立静态标题').toBeGreaterThan(500)
        expect(Math.abs((pdfSummary.blueCentroidX as number) - (pngSummary.blueCentroidX as number)))
          .toBeLessThan(0.01)
      }
      expect(file.length).toBeGreaterThan(4096)
      await expect.poll(() => observers.filter(item => item.kind === 'static-ready').length, { timeout: 30_000 })
        .toBeGreaterThan(priorSnapshots)
      const snapshots = observers.filter(item => item.kind === 'static-ready').slice(priorSnapshots)
      expect(snapshots.some(item => item.captureMode && item.execution === 'capture' && item.receipt?.status === 'ready'
        && item.media?.some(media => media.muted && media.paused))).toBe(true)
      // 离屏静态页不控制主画布媒体；导出全程主画布不新增播放。
      expect(observers.filter(item => item.kind === 'media-play').length).toBe(playsBefore)
      await dialog.getByRole('button', { name: '关闭', exact: true }).click()
      await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
      await expect(audio).toHaveJSProperty('paused', true)
    }

    await exportAndCheck('pptx-editable', 'HTML转PPTX')
    await exportAndCheck('canvas-pdf', '截图PDF')

    const priorSnapshots = observers.filter(item => item.kind === 'static-ready').length
    await runtime.locator('.nav-button--export').click()
    const dialog = runtime.locator('[role="dialog"][aria-labelledby="export-dialog-title"]')
    await dialog.getByText('截图PDF', { exact: true }).click()
    await dialog.getByText('所有页面', { exact: true }).click()
    await dialog.getByRole('button', { name: '开始导出' }).click()
    await expect(dialog.getByRole('button', { name: '取消导出' })).toBeVisible()
    await expect.poll(() => observers.filter(item => item.kind === 'static-ready').length, { timeout: 30_000 })
      .toBeGreaterThan(priorSnapshots)
    await dialog.getByRole('button', { name: '取消导出' }).click()
    await expect(dialog.getByRole('heading', { name: '导出失败' })).toBeVisible()
    await expect(dialog.getByText('用户取消导出')).toBeVisible()
    await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
    await expect(audio).toHaveJSProperty('paused', true)
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  } finally {
    for (const id of pageIds) {
      await api.patch(`/api/pages/${id}`, { data: { status: 'archived' } }).catch(() => undefined)
    }
  }
})

test('截图入口明确拒绝已移除的动画时刻选择器', async ({ context, visualEditSandbox }) => {
  const response = await context.request.post(`/api/pages/${visualEditSandbox.pageId}/screenshot-jobs`, {
    data: { motion_snapshot: { timeline_id: 'scene-export-isolation', at_ms: 6000, visual_mode: 'full' } },
  })
  expect(response.status()).toBe(422)
})
