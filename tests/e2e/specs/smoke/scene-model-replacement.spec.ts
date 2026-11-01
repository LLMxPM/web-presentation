/**
 * 文件功能：验证真实 GLB 替换后旧片段签名在新放映中明确失效，且不会回退到历史文件。
 * Scene 只在 prepare 时注册动作，因此失效证据来自正式放映的有界错误，而不是挂载期返回值。
 */
import { randomUUID } from 'node:crypto'
import { expect, test } from '../../fixtures/test-data'
import { buildSkinnedGlb } from '../../helpers/skinned-glb'

test('三维动作资源替换后旧签名在新放映中报失效', async ({ page, context, projectSandbox }) => {
  test.setTimeout(180_000)
  const api = context.request
  const name = `scene-model-replace-${randomUUID().slice(0, 8)}`
  const workspaceId = projectSandbox.workspaceId
  const upload = await api.post(`/api/workspaces/${workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${name}.glb`, mimeType: 'model/gltf-binary', buffer: buildSkinnedGlb(0.8) },
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

  const source = `<template><main ref="root" class="scene-model-replace-page">
    <AssetModel ref="model" name="${name}" class="scene-model-replace-target" />
  </main></template>
<script setup lang="ts">
import { ref } from 'vue'
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
import { usePageScene } from '@runtime-kit/public/composables/motion/usePageScene.v1'
import { useStaticPresentation } from '@runtime-kit/public/composables/static/useStaticPresentation.v1'
const root = ref<HTMLElement | null>(null)
const model = ref<InstanceType<typeof AssetModel> | null>(null)
useStaticPresentation({ root, mode: 'default' })
usePageScene({ root, define(scene) {
  const handle = model.value?.getHandle() ?? null
  if (!handle?.isReady()) throw new Error('模型尚未完成真实首帧，无法注册动作。')
  scene.onCleanup(handle.reset)
  scene.task(handle.animation({ id: 'bone', role: 'blocking', clipIndex: 0, signature: '${originalClip.signature}' }))
} })
</script>
<style scoped>.scene-model-replace-page{width:100%;height:100%;display:grid;place-items:center;background:#fff}.scene-model-replace-target{width:720px;height:480px}</style>`
  const updated = await api.patch(`/api/pages/${projectSandbox.pageId}`, { data: { page_content: source } })
  expect(updated.ok(), await updated.text()).toBeTruthy()
  const advance = await api.patch(`/api/projects/${projectSandbox.projectId}`, {
    data: { slideshow: {
      transition: { effect: 'none', duration_ms: 0 },
      advance: { mode: 'manual', delay_ms: 5000, completion_delay_ms: 300 },
      loop: false,
    } },
  })
  expect(advance.ok(), await advance.text()).toBeTruthy()

  /** 每次重新签发预览并进入放映，让 Scene 在真实首帧之后注册动作。 */
  async function playFreshPresentation() {
    const artifactResponse = await api.post(`/api/projects/${projectSandbox.projectId}/preview-artifacts`, { data: {} })
    expect(artifactResponse.ok(), await artifactResponse.text()).toBeTruthy()
    await page.goto((await artifactResponse.json()).preview_url as string)
    const frame = page.frameLocator('iframe#preview')
    // 预览保留打印副本，限定可见画布；透传 class 与模型数据属性位于同一根元素。
    const canvas = frame.locator('.page-content-wrapper')
    await expect(canvas.locator(`.scene-model-replace-target[data-runtime-asset-name="${name}"]`)).toHaveAttribute('data-runtime-model-state', 'ready', { timeout: 60_000 })
    await frame.getByRole('button', { name: '进入放映' }).click()
    return frame
  }

  const before = await playFreshPresentation()
  await expect(before.locator('.runtime-playback-error')).toHaveCount(0)
  await expect(before.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__state')).toHaveText('放映中')
  await before.getByRole('button', { name: '退出放映' }).click()

  const replace = await api.post(`/api/workspaces/${workspaceId}/assets/${asset.id}/replace`, {
    multipart: {
      file: { name: `${name}-new.glb`, mimeType: 'model/gltf-binary', buffer: buildSkinnedGlb(1.4) },
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

  const after = await playFreshPresentation()
  // 旧签名不按名称或时长放行；错误有界，不回退到历史文件。
  await expect(after.locator('.runtime-playback-error')).toContainText('签名已经失效', { timeout: 30_000 })
  await expect(after.getByRole('group', { name: '放映控制' }).locator('.runtime-playback-controls__state')).toHaveText('错误')
})
