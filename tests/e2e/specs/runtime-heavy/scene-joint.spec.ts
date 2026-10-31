/**
 * 文件功能：在真实预览与 Renderer 中联合验证三维动作、旁白、切页 cue 与 scene_end 放映的最小闭环。
 * 仅在显式选择联合验收实例时运行；C3 用同一入口执行真实发声、WebGL 与多窗口验收。
 */
import { randomUUID } from 'node:crypto'

import type { APIRequestContext } from '@playwright/test'

import { expect, test } from '../../fixtures/test-data'
import { buildToneWav } from '../../helpers/media-fixtures'
import { buildSkinnedGlb } from '../../helpers/skinned-glb'
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

test('三维动作、旁白和切页 cue 应在同一放映中协作，静态截图不被媒体阻塞', async (
  { page, context, visualEditSandbox }, testInfo,
) => {
  test.skip(process.env.SCENE_JOINT_ACCEPTANCE_ENABLED !== 'true', '仅在 Scene 联合验收实例运行')
  test.setTimeout(240_000)
  const api = context.request
  const slideshow = await api.get('/api/system/slideshow-capabilities')
  expect(slideshow.ok()).toBeTruthy()
  expect(await slideshow.json()).toMatchObject({
    schema_version: 4,
    advance_modes: ['manual', 'timer', 'scene_end'],
    audio: { page_narration: true, audio_cues: true },
  })
  const scene = await api.get('/api/system/scene-capabilities')
  expect(scene.ok()).toBeTruthy()
  expect(await scene.json()).toMatchObject({
    task_roles: ['blocking', 'ambient'],
    advance_modes: ['manual', 'timer', 'scene_end'],
    static_presentation: 'independent',
  })

  const suffix = randomUUID().slice(0, 8)
  const modelName = `joint-model-${suffix}`
  const narrationName = `joint-narration-${suffix}`
  const cueName = `joint-cue-${suffix}`
  const jointTitle = `联合验收页 ${suffix}`
  const modelResponse = await api.post(`/api/workspaces/${visualEditSandbox.workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${modelName}.glb`, mimeType: 'model/gltf-binary', buffer: buildSkinnedGlb(0.8) },
      asset_type: 'model3d', tags: '[]', name: modelName,
    },
  })
  expect(modelResponse.ok(), await modelResponse.text()).toBeTruthy()
  const model = await modelResponse.json() as {
    analysis_metadata: { model3d: { animations: Array<{ index: number; signature: string; duration_ms: number }> } }
  }
  // 片段索引与签名必须来自真实资源查询，不能凭名称或时长猜测。
  const clip = model.analysis_metadata.model3d.animations[0]
  expect(clip.signature).toBeTruthy()
  expect(clip.duration_ms).toBe(2000)
  const narrationId = await uploadAsset(api, visualEditSandbox.workspaceId, {
    name: narrationName, extension: 'wav', mimeType: 'audio/wav', kind: 'audio', bytes: buildToneWav(2_500),
  })
  expect(narrationId).toBeGreaterThan(0)
  const cueId = await uploadAsset(api, visualEditSandbox.workspaceId, {
    name: cueName, extension: 'wav', mimeType: 'audio/wav', kind: 'audio', bytes: buildToneWav(250),
  })

  const source = `<template>
  <main ref="root" class="w-full h-full p-8">
    <h1>${jointTitle}</h1>
    <AssetModel ref="model" name="${modelName}" class="w-full h-80" />
    <AssetAudio name="${narrationName}" purpose="narration" @media-ready="narration = $event" @media-unmounted="narration = null" />
  </main>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import AssetAudio from '@runtime-kit/public/components/assets/AssetAudio.v1.vue'
import { createSceneMediaTask } from '@runtime-kit/public/composables/media/createSceneMediaTask.v1'
import { useAudioCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
const model = ref<InstanceType<typeof AssetModel> | null>(null)
const narration = ref<HTMLMediaElement | null>(null)
const { playCue } = useAudioCue()
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  const handle = model.value?.getHandle() ?? null
  if (!handle?.isReady()) throw new Error('联合样例需要已完成真实首帧的模型。')
  scene.onCleanup(handle.reset)
  scene.task(handle.animation({ id: 'action', role: 'blocking', clipIndex: ${clip.index}, signature: '${clip.signature}' }))
  scene.task(createSceneMediaTask({ id: 'narration', role: 'blocking', afterTrack: 'action', target: () => narration.value }))
  scene.task({ id: 'finish-cue', role: 'ambient', afterTrack: 'narration', async run() { await playCue('interaction.joint-finished') } })
} })
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
          advance: { mode: 'scene_end', delay_ms: 5_000, completion_delay_ms: 300 },
          loop: false,
        },
        audio_settings: {
          master_volume_percent: 100,
          narration_volume_percent: 100,
          effects_volume_percent: 100,
          cue_bindings: [
            { key: 'transition.forward', asset_id: cueId, gain_percent: 100 },
            { key: 'interaction.joint-finished', asset_id: cueId, gain_percent: 100 },
          ],
        },
      },
    })
    expect(settings.ok(), await settings.text()).toBeTruthy()
    const routes = await api.put(`/api/projects/${visualEditSandbox.projectId}/routes`, {
      data: {
        routes: [
          {
            route_type: 'page', route: 'home', order: 0, hidden: false, page_id: visualEditSandbox.pageId,
            advance: { mode: 'manual', delay_ms: 5_000, completion_delay_ms: 300 },
          },
          { route_type: 'page', route: 'joint', order: 1, hidden: false, page_id: jointPageId },
        ],
      },
    })
    expect(routes.ok(), await routes.text()).toBeTruthy()

    // 静态捕获必须等待 GLB 首帧，同时不播放旁白、不推进 Mixer。
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
    const pngResponse = await api.get((await details.json()).screenshot_url as string)
    expect(pngResponse.ok()).toBeTruthy()
    const png = Buffer.from(await pngResponse.body())
    await testInfo.attach('joint-static.png', { body: png, contentType: 'image/png' })
    const pixels = decodePngPixels(png)
    expect(countStrongRedPixels(pixels) / (pixels.width * pixels.height)).toBeGreaterThan(0.001)

    // 记录真实 HTMLMediaElement.play 调用，区分切页 cue、结束 cue 与页面旁白的资源地址。
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
    await page.goto((await artifactResponse.json()).preview_url as string)
    const runtime = page.frameLocator('iframe#preview')
    await expect(runtime.getByRole('heading', { name: visualEditSandbox.pageTitle }).last()).toBeVisible()
    await runtime.locator('button[title="进入放映"]').click()
    const controls = runtime.getByRole('group', { name: '放映控制' })
    await expect(controls.locator('[data-testid="playback-remaining"]')).toHaveText('本页手动')
    await controls.getByRole('button', { name: '下一页' }).click()
    await expect(runtime.getByRole('heading', { name: jointTitle }).last()).toBeVisible()
    // scene_end 等待模型动作与旁白实际结束；旁白必须真实推进，不用时长估计。
    await expect.poll(() => runtime.locator('[data-runtime-media-purpose="narration"]').evaluate(
      element => (element as HTMLAudioElement).currentTime,
    ), { timeout: 20_000 }).toBeGreaterThan(0)
    await expect.poll(() => runtime.locator('body').evaluate(() => {
      const sources = (window as Window & { __jointAudioPlaySources?: string[] }).__jointAudioPlaySources || []
      return new Set(sources.filter(Boolean)).size
    }), { timeout: 30_000 }).toBeGreaterThanOrEqual(2)
    await expect(controls.locator('.runtime-playback-controls__state')).toHaveText('放映中')
  } finally {
    await api.patch(`/api/pages/${jointPageId}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})
