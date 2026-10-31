/**
 * 文件功能：在受保护预览域上复现受控慢速传输，验证媒体进入 waiting 后仍能在数据到达时恢复播放。
 *
 * 慢速通过挂起受保护媒体请求、在断言 waiting 后再放行实现；延迟发生在播放阶段而不是预加载阶段，
 * 否则小文件会在 metadata 预取时就把延迟消耗掉，测不到 waiting。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { expect, test } from '../../fixtures/test-data'
import { writeEvidence } from '../../helpers/c3-probes'
import {
  archiveSandboxPage,
  createSandboxPage,
  publishRoutes,
  runtimeFrame,
  uploadSandboxAsset,
} from '../../helpers/scene-sandbox'

/** 等待媒体进入 waiting 的上限；超过则认为慢速条件未真正建立。 */
const WAITING_TIMEOUT_MS = 15_000
/** 放行后恢复播放的上限。 */
const RECOVERY_TIMEOUT_MS = 30_000

/** 受保护视频页：单个静音视频，便于唯一发声/唯一媒体判定。 */
function buildSlowMediaPage(videoName: string): string {
  return `<template>
  <main ref="root" class="slow-media-page">
    <h1 class="slow-media-title">受保护慢速媒体</h1>
    <AssetVideo name="${videoName}" muted class="slow-media-video" />
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
</script>
<style scoped>
.slow-media-page { width: 100%; height: 100%; display: grid; place-content: center; justify-items: center; gap: 12px; background: #f8fafc; }
.slow-media-title { font-size: 32px; color: #0f172a; }
.slow-media-video { width: 480px; height: 270px; object-fit: cover; border-radius: 8px; }
</style>`
}

test('受保护媒体慢速传输：进入 waiting 并在数据到达后恢复播放', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(4 * 60_000)
  const api = context.request
  const suffix = `slow-${Date.now()}`
  const videoName = `${suffix}-video`
  const createdPages: number[] = []

  await uploadSandboxAsset(api, visualEditSandbox.workspaceId, {
    name: videoName,
    type: 'video',
    mimeType: 'video/webm',
    fileName: `${videoName}.webm`,
    buffer: readFileSync(resolve('runtime/public/video/runtime-video-showcase.webm')),
  })

  // 挂起受保护媒体请求：先让播放进入 waiting，再放行，模拟真实慢速传输的恢复过程。
  // 受保护资源地址不带固定扩展名，必须按资源类型识别，不能按 .webm 后缀匹配。
  let releaseMedia: (() => void) | null = null
  const mediaGate = new Promise<void>(resolveGate => {
    releaseMedia = resolveGate
  })
  let mediaRequests = 0
  const mediaUrls: string[] = []
  await context.route('**/preview/artifacts/**', async route => {
    if (route.request().resourceType() !== 'media') {
      await route.continue()
      return
    }
    mediaRequests += 1
    mediaUrls.push(new URL(route.request().url()).pathname)
    await mediaGate
    await route.continue()
  })

  try {
    const pageId = await createSandboxPage(api, visualEditSandbox, `${suffix} 慢速媒体页`, buildSlowMediaPage(videoName))
    createdPages.push(pageId)
    const previewUrl = await publishRoutes(api, visualEditSandbox.projectId, [{ route: 'slow-media', pageId }])
    await page.goto(previewUrl)
    const frame = await runtimeFrame(page)
    const video = frame.locator('.page-content-wrapper video')
    await expect(video).toBeVisible()
    await expect
      .poll(() => video.evaluate(element => (element as HTMLVideoElement).currentSrc), { timeout: 20_000 })
      .not.toBe('')

    // 先挂事件监听再触发播放：waiting 必须在数据到达前发生。
    await video.evaluate(element => {
      const media = element as HTMLVideoElement
      const state = { waiting: 0, playing: 0, stalled: 0, canplay: 0, errors: [] as string[] }
      ;(window as unknown as { __c3Media: typeof state }).__c3Media = state
      media.addEventListener('waiting', () => { state.waiting += 1 })
      media.addEventListener('playing', () => { state.playing += 1 })
      media.addEventListener('stalled', () => { state.stalled += 1 })
      media.addEventListener('canplay', () => { state.canplay += 1 })
      media.addEventListener('error', () => { state.errors.push(media.error?.code ? String(media.error.code) : 'unknown') })
      media.muted = true
      void media.play().catch(error => { state.errors.push(`play:${(error as Error).name}`) })
    })

    await expect
      .poll(() => video.evaluate(() => (window as unknown as { __c3Media?: { waiting: number } }).__c3Media?.waiting ?? 0), {
        timeout: WAITING_TIMEOUT_MS,
        message: '受控慢速传输下媒体未进入 waiting',
      })
      .toBeGreaterThan(0)

    // 断言 waiting 成立后再放行媒体请求，验证数据到达即可恢复。
    releaseMedia?.()

    await expect
      .poll(() => video.evaluate(() => (window as unknown as { __c3Media?: { playing: number } }).__c3Media?.playing ?? 0), {
        timeout: RECOVERY_TIMEOUT_MS,
        message: '数据到达后媒体未恢复播放',
      })
      .toBeGreaterThan(0)

    const facts = await video.evaluate(element => {
      const media = element as HTMLVideoElement
      const state = (window as unknown as { __c3Media?: Record<string, unknown> }).__c3Media ?? {}
      return {
        mediaState: state,
        currentTime: media.currentTime,
        readyState: media.readyState,
        networkState: media.networkState,
        duration: Number.isFinite(media.duration) ? media.duration : null,
        pageVideoElements: document.querySelectorAll('.page-content-wrapper video').length,
        documentVideoElements: document.querySelectorAll('video').length,
        audioElements: document.querySelectorAll('audio').length,
        currentSrcIsProtectedPreview: media.currentSrc.includes('/preview/artifacts/'),
      }
    })

    const evidence = {
      kind: 'c3-protected-media-slow',
      generatedAt: new Date().toISOString(),
      candidateCommit: process.env.C3_CANDIDATE_COMMIT ?? 'working-tree',
      heldMediaRequests: mediaRequests,
      waitingTimeoutMs: WAITING_TIMEOUT_MS,
      facts,
    }
    const evidencePath = await writeEvidence(testInfo, `protected-media-slow-${suffix}`, evidence)
    testInfo.annotations.push({ type: 'evidence', description: evidencePath })
    console.log(`[c3-slow-media] ${JSON.stringify({ mediaRequests, ...facts.mediaState })}`)

    // 只约束页面内容区的视频数量；运行时外壳自身不属于页面内容。
    expect(facts.pageVideoElements, '页面内容区出现多个视频元素，无法证明唯一媒体').toBe(1)
    expect(facts.currentSrcIsProtectedPreview, '媒体未走受保护预览地址').toBe(true)
    expect(facts.readyState, '恢复后仍未具备可播放数据').toBeGreaterThanOrEqual(2)
  } finally {
    await context.unroute('**/preview/artifacts/**').catch(() => undefined)
    for (const pageId of createdPages) await archiveSandboxPage(api, pageId)
  }
})
