/**
 * 文件功能：验证独立预览域中受保护视频和音频的 HEAD、Range 与真实定位。
 */
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from '../../fixtures/test-data'
import { shortWavBuffer } from '../../helpers/motion-media'

test('受保护视频和音频支持 HEAD、Range 与视频跳转定位', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const suffix = randomUUID().slice(0, 8)
  const videoName = `motion-video-${suffix}`
  const audioName = `motion-audio-${suffix}`
  const videoBytes = readFileSync(resolve('runtime/public/video/runtime-video-showcase.webm'))
  for (const asset of [
    { name: videoName, type: 'video', mime: 'video/webm', file: `${videoName}.webm`, bytes: videoBytes },
    { name: audioName, type: 'audio', mime: 'audio/wav', file: `${audioName}.wav`, bytes: shortWavBuffer() },
  ]) {
    const uploaded = await api.post(`/api/workspaces/${visualEditSandbox.workspaceId}/assets/upload`, {
      multipart: {
        file: { name: asset.file, mimeType: asset.mime, buffer: asset.bytes },
        asset_type: asset.type,
        tags: '[]',
        name: asset.name,
      },
    })
    expect(uploaded.ok(), await uploaded.text()).toBeTruthy()
  }
  const source = `<template><main class="motion-protected-media">
  <AssetVideo name="${videoName}" class="motion-protected-video" />
  <AssetAudio name="${audioName}" class="motion-protected-audio" />
</main></template>
<script setup lang="ts">
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v2.vue'
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v2.vue'
</script>`
  const updated = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()
  const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
  expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
  const artifact = await artifactResponse.json() as { preview_url: string }
  await page.goto(artifact.preview_url)
  const runtime = page.frameLocator('iframe#preview')
  const video = runtime.locator('.page-content-wrapper .motion-protected-media video')
  const audio = runtime.locator('.page-content-wrapper .motion-protected-media audio')
  await expect(video).toBeVisible()
  await expect.poll(() => video.evaluate(element => (element as HTMLVideoElement).currentSrc)).not.toBe('')
  await expect.poll(() => audio.evaluate(element => (element as HTMLAudioElement).currentSrc)).not.toBe('')
  const protectedUrls: string[] = []
  for (const media of [video, audio]) {
    const result = await media.evaluate(async element => {
      const url = (element as HTMLMediaElement).currentSrc
      const head = await fetch(url, { method: 'HEAD' })
      const range = await fetch(url, { headers: { Range: 'bytes=0-511' } })
      return {
        url,
        headStatus: head.status,
        headLength: head.headers.get('content-length'),
        rangeStatus: range.status,
        rangeLength: (await range.arrayBuffer()).byteLength,
      }
    })
    expect(result.url).toContain('/preview/artifacts/')
    protectedUrls.push(result.url)
    expect(result.headStatus).toBe(200)
    expect(Number(result.headLength)).toBeGreaterThan(512)
    expect(result.rangeStatus).toBe(206)
    expect(result.rangeLength).toBe(512)
  }
  for (const url of protectedUrls) {
    const withoutTicket = new URL(url)
    withoutTicket.searchParams.delete('token')
    const head = await api.head(withoutTicket.toString())
    const range = await api.get(withoutTicket.toString(), { headers: { Range: 'bytes=0-511' } })
    expect([401, 403]).toContain(head.status())
    expect([401, 403]).toContain(range.status())
  }
  const seek = await video.evaluate(async element => {
    const media = element as HTMLVideoElement
    if (media.readyState < 1) await new Promise<void>(resolveReady => media.addEventListener('loadedmetadata', () => resolveReady(), { once: true }))
    const target = Math.min(1, media.duration / 2)
    media.currentTime = target
    if (media.seeking) await new Promise<void>(resolveSeek => media.addEventListener('seeked', () => resolveSeek(), { once: true }))
    return { target, currentTime: media.currentTime, readyState: media.readyState }
  })
  expect(seek.readyState).toBeGreaterThanOrEqual(2)
  expect(Math.abs(seek.currentTime - seek.target)).toBeLessThan(0.1)
})
