/**
 * 文件功能：在隔离的指定状态捕获入口验证真实骨骼动画 GLB 的远程静态采样。
 */
import { randomUUID } from 'node:crypto'
import { expect, test } from '../../fixtures/test-data'
import { buildSkinnedMotionGlb } from '../../helpers/motion-skinned-model'
import { countStrongRedPixels, decodePngPixels, type DecodedPng } from '../../helpers/png-pixels'

test.skip(process.env.MOTION_CAPTURE_TEST_OPT_IN !== '1', '仅临时测试入口开启指定状态捕获时运行')

/** 计算红色模型像素的水平重心，反映骨骼平移后的几何变化。 */
function redCentroidX(image: DecodedPng): number {
  let xTotal = 0
  let count = 0
  for (let y = 0; y < image.height; y += 1) {
    for (let x = 0; x < image.width; x += 1) {
      const at = (y * image.width + x) * image.channels
      const [red, green, blue] = image.pixels.subarray(at, at + 3)
      if (red > 120 && red - green > 40 && red - blue > 40) {
        xTotal += x
        count += 1
      }
    }
  }
  expect(count / (image.width * image.height)).toBeGreaterThan(0.002)
  return xTotal / count
}

test('远程截图在骨骼片段 0ms 与 1000ms 显示不同几何位置', async ({ context, visualEditSandbox }, testInfo) => {
  test.setTimeout(240_000)
  const api = context.request
  const pageId = visualEditSandbox.pageId
  const name = `motion-bone-${randomUUID().slice(0, 8)}`
  const upload = await api.post(`/api/workspaces/${visualEditSandbox.workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${name}.glb`, mimeType: 'model/gltf-binary', buffer: buildSkinnedMotionGlb() },
      asset_type: 'model3d',
      tags: '[]',
      name,
    },
  })
  expect(upload.ok(), await upload.text()).toBeTruthy()
  const source = `<template><main ref="root" class="motion-bone-page"><AssetModel name="${name}" class="motion-bone-model" /></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v2.vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({ root, bindings: {}, applyPoster: true,
  definition: { schemaVersion: 1, timelineId: 'bone-capture-e2e', poster: { atMs: 0 },
    tracks: [{ type: 'model3d', id: 'bone', asset: '${name}', selector: '.motion-bone-model',
      clip: { index: 0, name: 'BoneSlide', durationMs: 2000 }, outMs: 2000 }] } })
</script>
<style scoped>.motion-bone-page{width:100%;height:100%;display:grid;place-items:center;background:#fff}.motion-bone-model{width:720px;height:480px}</style>`
  const updated = await api.patch(`/api/pages/${pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()

  /** 执行 Backend→Renderer→Runtime 指定状态捕获，并保留 PNG 供失败排障。 */
  async function capture(atMs: number) {
    const response = await api.post(`/api/pages/${pageId}/screenshot-jobs`, {
      data: { motion_snapshot: { timeline_id: 'bone-capture-e2e', at_ms: atMs, visual_mode: 'full' } },
    })
    expect(response.ok(), await response.text()).toBeTruthy()
    const job = await response.json() as { id: number }
    let applied: { status: string; sampled_time_ms: number } | null = null
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
    await testInfo.attach(`bone-${atMs}.png`, { body: png, contentType: 'image/png' })
    return decodePngPixels(png)
  }

  const start = await capture(0)
  const middle = await capture(1000)
  expect(countStrongRedPixels(start)).toBeGreaterThan(0)
  expect(redCentroidX(middle) - redCentroidX(start)).toBeGreaterThan(5)
})
