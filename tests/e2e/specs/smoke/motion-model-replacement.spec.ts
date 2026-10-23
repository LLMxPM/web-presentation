/**
 * 文件功能：验证真实 GLB 替换后旧动作签名在新预览中明确失效，且不会回退到历史文件。
 */
import { randomUUID } from 'node:crypto'
import { expect, test } from '../../fixtures/test-data'
import { buildSkinnedMotionGlb } from '../../helpers/motion-skinned-model'

test('三维动作资源替换后旧签名在新预览中报 stale', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const name = `motion-model-replace-${randomUUID().slice(0, 8)}`
  const workspaceId = visualEditSandbox.workspaceId
  const upload = await api.post(`/api/workspaces/${workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${name}.glb`, mimeType: 'model/gltf-binary', buffer: buildSkinnedMotionGlb(0.8) },
      asset_type: 'model3d', tags: '[]', name,
    },
  })
  expect(upload.ok(), await upload.text()).toBeTruthy()
  const asset = await upload.json() as {
    id: number; file_hash: string
    analysis_metadata: { model3d: { animations: Array<{ signature: string; duration_ms: number }> } }
  }
  const originalClip = asset.analysis_metadata.model3d.animations[0]
  expect(originalClip.signature).toBeTruthy()
  expect(originalClip.duration_ms).toBe(2000)

  const source = `<template><main ref="root" class="motion-model-replace-page">
    <AssetModel name="${name}" class="motion-model-replace-target" />
    <output data-testid="motion-model-error">{{ error ? error.code : 'ready' }}</output>
  </main></template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v2.vue'
import { usePageTimeline } from '@runtime-kit/public/composables/motion/usePageTimeline.v1'
const root = ref<HTMLElement | null>(null)
const { error } = usePageTimeline({ root, bindings: {}, applyPoster: true,
  definition: { schemaVersion: 1, timelineId: 'model-replacement', poster: { atMs: 0 },
    tracks: [{ type: 'model3d', id: 'bone', asset: '${name}', selector: '.motion-model-replace-target',
      clip: { index: 0, name: 'BoneSlide', durationMs: 2000, signature: '${originalClip.signature}' }, outMs: 2000 }] } })
</script>
<style scoped>.motion-model-replace-page{width:100%;height:100%;display:grid;place-items:center;background:#fff}.motion-model-replace-target{width:720px;height:480px}output{position:absolute;left:16px;bottom:16px}</style>`
  const updated = await api.patch(`/api/pages/${visualEditSandbox.pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()

  /** 每次重新签发预览，让 Runtime 读取当前资源哈希并初始化模型时间轴。 */
  async function openFreshPreview() {
    const artifactResponse = await api.post(`/api/projects/${visualEditSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    const artifact = await artifactResponse.json() as { preview_url: string }
    await page.goto(artifact.preview_url)
    const frame = page.frameLocator('iframe#preview')
    // 预览同时保留导出打印源副本，必须限定在可见画布内断言。
    const canvas = frame.locator('.page-content-wrapper')
    await expect(canvas.locator(`.motion-model-replace-target[data-runtime-asset-name="${name}"]`)).toHaveAttribute('data-runtime-model-state', 'ready')
    return canvas.locator('[data-testid="motion-model-error"]')
  }

  const before = await openFreshPreview()
  await expect(before).toHaveText('ready')

  const replace = await api.post(`/api/workspaces/${workspaceId}/assets/${asset.id}/replace`, {
    multipart: {
      file: { name: `${name}-new.glb`, mimeType: 'model/gltf-binary', buffer: buildSkinnedMotionGlb(1.4) },
      expected_file_hash: asset.file_hash,
    },
  })
  expect(replace.ok(), await replace.text()).toBeTruthy()
  const replaced = await replace.json() as {
    file_hash: string
    analysis_metadata: { model3d: { animations: Array<{ signature: string }> } }
  }
  expect(replaced.file_hash).not.toBe(asset.file_hash)
  expect(replaced.analysis_metadata.model3d.animations[0].signature).not.toBe(originalClip.signature)

  const after = await openFreshPreview()
  await expect(after).toHaveText('MODEL_ANIMATION_REFERENCE_STALE')
})
