/**
 * 文件功能：验证时间轴页面引用的资源被合法替换后，新预览刷新内容身份和真实像素。
 */
import { randomUUID } from 'node:crypto'
import { expect, test } from '../../fixtures/test-data'
import { countPixels, decodePngPixels } from '../../helpers/png-pixels'

/** 创建纯色 SVG；通过实际资源上传与替换接口进入受保护预览。 */
function solidSvg(color: string): Buffer {
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" fill="${color}"/></svg>`)
}

test('时间轴页面合法替换图片后刷新资源身份和预览像素', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  const name = `motion-replace-${randomUUID().slice(0, 8)}`
  const workspaceId = visualEditSandbox.workspaceId
  const upload = await api.post(`/api/workspaces/${workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${name}.svg`, mimeType: 'image/svg+xml', buffer: solidSvg('#e11d48') },
      asset_type: 'image',
      tags: '[]',
      name,
    },
  })
  expect(upload.ok(), await upload.text()).toBeTruthy()
  const created = await upload.json() as { id: number; file_hash: string }
  const source = `<template><main ref="root" class="motion-replace-page"><AssetImage name="${name}" alt="替换验证" class="motion-replace-image" /></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
usePageTimeline({ root, bindings: { image: '.motion-replace-image' }, applyPoster: true,
  definition: { schemaVersion: 1, timelineId: 'replace-image', poster: { atMs: 100 },
    tracks: [{ type: 'dom', id: 'image', target: 'image', preset: 'fade', durationMs: 100 }] } })
</script>
<style scoped>.motion-replace-page{width:100%;height:100%;display:grid;place-items:center;background:#fff}.motion-replace-image{width:256px;height:256px;object-fit:fill}</style>`
  const updated = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()

  /** 构建独立预览并读取真实 img 来源和图像像素。 */
  async function previewImage() {
    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    const artifact = await artifactResponse.json() as { preview_url: string }
    await page.goto(artifact.preview_url)
    const image = page.frameLocator('iframe#preview').locator('.page-content-wrapper img[alt="替换验证"]')
    await expect(image).toBeVisible()
    await expect(image).toHaveJSProperty('naturalWidth', 256)
    const sourceUrl = await image.getAttribute('src')
    expect(sourceUrl).toBeTruthy()
    return { sourceUrl: sourceUrl!, pixels: decodePngPixels(await image.screenshot()) }
  }

  const before = await previewImage()
  expect(before.sourceUrl).toContain(created.file_hash)
  expect(countPixels(before.pixels, (r, g, b) => r > 160 && r > g * 1.6 && r > b * 1.3) / (before.pixels.width * before.pixels.height)).toBeGreaterThan(0.7)

  const replace = await api.post(`/api/workspaces/${workspaceId}/assets/${created.id}/replace`, {
    multipart: { file: { name: `${name}-blue.svg`, mimeType: 'image/svg+xml', buffer: solidSvg('#2563eb') } },
  })
  expect(replace.ok(), await replace.text()).toBeTruthy()
  const replaced = await replace.json() as { file_hash: string }
  expect(replaced.file_hash).not.toBe(created.file_hash)
  const after = await previewImage()
  expect(after.sourceUrl).toContain(replaced.file_hash)
  expect(after.sourceUrl).not.toBe(before.sourceUrl)
  expect(countPixels(after.pixels, (r, g, b) => b > 160 && b > r * 1.5 && b > g * 1.2) / (after.pixels.width * after.pixels.height)).toBeGreaterThan(0.7)
})
