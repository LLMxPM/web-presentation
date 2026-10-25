/**
 * 文件功能：在真实预览与 Renderer 中联合验证 3D、旁白、切页 cue 和自动放映的最小闭环。
 * 仅在显式选择联合验收用例时运行，旁白与 cue 已作为默认音频能力开放。
 */
import { randomUUID } from 'node:crypto'

import type { APIRequestContext } from '@playwright/test'

import { expect, test } from '../../fixtures/test-data'
import { buildRedModelGlb, buildToneWav } from '../../helpers/media-fixtures'
import { countStrongRedPixels, decodePngPixels } from '../../helpers/png-pixels'

/** 上传真实测试字节并返回资源 ID，失败时保留服务端业务错误。 */
async function uploadAsset(
  api: APIRequestContext,
  workspaceId: number,
  input: { name: string; extension: string; mimeType: string; kind: string; bytes: Buffer },
): Promise<number> {
  const response = await api.post(`/api/workspaces/${workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${input.name}.${input.extension}`, mimeType: input.mimeType, buffer: input.bytes },
      asset_type: input.kind,
      tags: '[]',
      name: input.name,
    },
  })
  expect(response.ok(), await response.text()).toBeTruthy()
  return Number((await response.json()).id)
}

test('3D、旁白和切页 cue 应在同一放映中协作，静态截图不被媒体阻塞', async (
  { page, context, visualEditSandbox }, testInfo,
) => {
  test.skip(process.env.PRE_MOTION_ACCEPTANCE_ENABLED !== 'true', '仅在音频联合验收实例运行')
  test.setTimeout(240_000)
  const api = context.request
  const capabilities = await api.get('/api/system/slideshow-capabilities')
  expect(capabilities.ok()).toBeTruthy()
  expect((await capabilities.json()).audio).toMatchObject({ page_narration: true, audio_cues: true })

  const suffix = randomUUID().slice(0, 8)
  const modelName = `joint-model-${suffix}`
  const narrationName = `joint-narration-${suffix}`
  const cueName = `joint-cue-${suffix}`
  const jointTitle = `联合验收页 ${suffix}`
  await uploadAsset(api, visualEditSandbox.workspaceId, {
    name: modelName, extension: 'glb', mimeType: 'model/gltf-binary', kind: 'model3d', bytes: buildRedModelGlb(),
  })
  await uploadAsset(api, visualEditSandbox.workspaceId, {
    name: narrationName, extension: 'wav', mimeType: 'audio/wav', kind: 'audio', bytes: buildToneWav(2_500),
  })
  const cueId = await uploadAsset(api, visualEditSandbox.workspaceId, {
    name: cueName, extension: 'wav', mimeType: 'audio/wav', kind: 'audio', bytes: buildToneWav(250),
  })

  const source = `<template>
  <main class="w-full h-full p-8">
    <h1>${jointTitle}</h1>
    <AssetModel name="${modelName}" class="w-full h-80" />
    <AssetAudio name="${narrationName}" purpose="narration" />
  </main>
</template>
<script setup lang="ts">
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'
</script>`
  const created = await api.post('/api/pages', {
    data: {
      workspace_id: visualEditSandbox.workspaceId,
      project_id: visualEditSandbox.projectId,
      title: jointTitle,
      file_type: 'vue',
      page_content: source,
    },
  })
  expect(created.ok(), await created.text()).toBeTruthy()
  const jointPageId = Number((await created.json()).id)

  try {
    const settings = await api.patch(`/api/projects/${visualEditSandbox.projectId}`, {
      data: {
        slideshow: {
          transition: { effect: 'push', duration_ms: 300 },
          advance: { mode: 'media_end', delay_ms: 1_000, media_timeout_ms: 10_000 },
          loop: false,
          auto_start: true,
        },
        audio_settings: {
          master_volume_percent: 100,
          narration_volume_percent: 100,
          effects_volume_percent: 100,
          cue_bindings: [{ key: 'transition.forward', asset_id: cueId, gain_percent: 100 }],
        },
      },
    })
    expect(settings.ok(), await settings.text()).toBeTruthy()
    const routes = await api.put(`/api/projects/${visualEditSandbox.projectId}/routes`, {
      data: {
        routes: [
          {
            route_type: 'page', route: 'home', order: 0, hidden: false,
            page_id: visualEditSandbox.pageId,
            advance: { mode: 'manual', delay_ms: 1_000, media_timeout_ms: 10_000 },
          },
          { route_type: 'page', route: 'joint', order: 1, hidden: false, page_id: jointPageId },
        ],
      },
    })
    expect(routes.ok(), await routes.text()).toBeTruthy()

    // 静态捕获必须等待 GLB 首帧，同时忽略旁白与自动翻页。
    const jobResponse = await api.post(`/api/pages/${jointPageId}/screenshot-jobs`, { data: {} })
    expect(jobResponse.ok(), await jobResponse.text()).toBeTruthy()
    const jobId = Number((await jobResponse.json()).id)
    await expect.poll(async () => {
      const response = await api.get(`/api/pages/screenshot-jobs/${jobId}`)
      expect(response.ok()).toBeTruthy()
      const job = await response.json()
      return { status: job.status, error: job.error_code }
    }, { timeout: 120_000, intervals: [1_000, 2_000] }).toEqual({ status: 'succeeded', error: null })
    const details = await api.get(`/api/pages/${jointPageId}`)
    expect(details.ok()).toBeTruthy()
    const screenshotUrl = (await details.json()).screenshot_url as string
    const pngResponse = await api.get(screenshotUrl)
    expect(pngResponse.ok()).toBeTruthy()
    const png = Buffer.from(await pngResponse.body())
    await testInfo.attach('joint-static.png', { body: png, contentType: 'image/png' })
    const pixels = decodePngPixels(png)
    expect(countStrongRedPixels(pixels) / (pixels.width * pixels.height)).toBeGreaterThan(0.005)

    // 记录真实 HTMLMediaElement.play 调用，区分切页 cue 与页面旁白的资源地址。
    await context.addInitScript(() => {
      const sources: string[] = []
      Object.assign(window, { __jointAudioPlaySources: sources })
      const originalPlay = HTMLMediaElement.prototype.play
      HTMLMediaElement.prototype.play = function () {
        sources.push(this.currentSrc || this.src)
        return originalPlay.call(this)
      }
    })
    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, {
      data: { entry_descriptor: { entry_type: 'route', route: '/home' } },
    })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    await page.goto((await artifactResponse.json()).preview_url)
    const runtime = page.frameLocator('iframe#preview')
    await expect(runtime.getByRole('heading', { name: visualEditSandbox.pageTitle }).last()).toBeVisible()
    await runtime.locator('button[title="进入放映"]').click()
    await expect(runtime.locator('[data-testid="playback-auto-toggle"]')).toBeVisible()
    await runtime.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(runtime.getByRole('heading', { name: jointTitle }).last()).toBeVisible()
    await expect.poll(() => runtime.locator('[data-runtime-media-purpose="narration"]').evaluate(
      element => (element as HTMLAudioElement).currentTime,
    ), { timeout: 10_000 }).toBeGreaterThan(0)
    await expect.poll(() => runtime.locator('body').evaluate(() => {
      const sources = (window as Window & { __jointAudioPlaySources?: string[] }).__jointAudioPlaySources || []
      return new Set(sources.filter(Boolean)).size
    }), { timeout: 10_000 }).toBeGreaterThanOrEqual(2)
  } finally {
    await api.patch(`/api/pages/${jointPageId}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})
