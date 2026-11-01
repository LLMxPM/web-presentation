/**
 * 文件功能：验证 Scene 页面引用的资源被合法替换后，新预览刷新内容身份和真实像素。
 */
import { randomUUID } from 'node:crypto'
import { expect, test } from '../../fixtures/test-data'
import { countPixels, decodePngPixels } from '../../helpers/png-pixels'

/** 创建纯色 SVG；通过实际资源上传与替换接口进入受保护预览。 */
function solidSvg(color: string): Buffer {
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" fill="${color}"/></svg>`)
}

test('Scene 页面合法替换图片后刷新资源身份和预览像素', async ({ page, context, projectSandbox }) => {
  test.setTimeout(120_000)
  const api = context.request
  const name = `scene-replace-${randomUUID().slice(0, 8)}`
  const workspaceId = projectSandbox.workspaceId
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
  const source = `<template><main ref="root" class="scene-replace-page"><AssetImage name="${name}" alt="替换验证" class="scene-replace-image" /></main></template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  scene.visual({ id: 'image', role: 'blocking', define(timeline) {
    timeline.fromTo('.scene-replace-image', { opacity: 0 }, { opacity: 1, duration: 0.1, ease: 'none' })
  } })
} })
</script>
<style scoped>.scene-replace-page{width:100%;height:100%;display:grid;place-items:center;background:#fff}.scene-replace-image{width:256px;height:256px;object-fit:fill}</style>`
  const updated = await api.patch(`/api/pages/${projectSandbox.pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()

  /** 构建独立预览并读取真实 img 来源和图像像素。 */
  async function previewImage() {
    const artifactResponse = await api.post(`/api/projects/${projectSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    await page.goto((await artifactResponse.json()).preview_url as string)
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
