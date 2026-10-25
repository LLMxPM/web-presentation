/**
 * 文件功能：通过独立页面验证 Backend→Renderer→Runtime 真实截图与 PNG 产物链路。
 */
import { randomUUID } from 'node:crypto'

import { expect, test } from '../../fixtures/test-data'
import { buildRedModelGlb } from '../../helpers/media-fixtures'
import { countStrongRedPixels, decodePngPixels } from '../../helpers/png-pixels'

test('页面截图应通过远程 Renderer 生成可下载 PNG', async ({ page, context, visualEditSandbox }, testInfo) => {
  test.setTimeout(180_000)
  const { workspaceId, projectId, pageId, pageTitle } = visualEditSandbox
  await page.goto(`/workspaces/${workspaceId}/projects/${projectId}/pages`)
  await expect(page.locator('[data-testid="batch-refresh-routed-page-screenshots"]')).toBeVisible()

  const firstCard = page.locator('[data-testid="page-card"]').filter({
    has: page.getByRole('button', { name: `复制页面名称：${pageTitle}`, exact: true }),
  })
  await firstCard.hover()
  await expect(firstCard.locator('[data-testid="page-card-screenshot"]')).toBeVisible()
  const createdResponse = page.waitForResponse(response =>
    response.request().method() === 'POST' && response.url().endsWith(`/api/pages/${pageId}/screenshot-jobs`),
  )
  await firstCard.locator('[data-testid="page-card-screenshot"]').click()
  const response = await createdResponse
  expect(response.ok(), await response.text()).toBeTruthy()
  const job = await response.json()
  await expect.poll(async () => {
    const statusResponse = await context.request.get(`/api/pages/screenshot-jobs/${job.id}`)
    expect(statusResponse.ok()).toBeTruthy()
    const result = await statusResponse.json()
    return { status: result.status, error: result.error_code }
  }, { timeout: 120_000, intervals: [1000, 2000] }).toEqual({ status: 'succeeded', error: null })

  const detailsResponse = await context.request.get(`/api/pages/${pageId}`)
  expect(detailsResponse.ok()).toBeTruthy()
  const details = await detailsResponse.json()
  expect(details.screenshot_is_latest).toBe(true)
  expect(details.screenshot_url).toBeTruthy()
  const imageResponse = await context.request.get(details.screenshot_url)
  expect(imageResponse.ok()).toBeTruthy()
  expect(imageResponse.headers()['content-type']).toContain('image/png')
  const png = await imageResponse.body()
  expect(png.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  expect(png.readUInt32BE(16)).toBe(job.viewport_width)
  expect(png.readUInt32BE(20)).toBe(job.viewport_height)
  // 浏览器中的私有截图应通过登录所在的 API 入口加载，覆盖公开基址别名导致 Cookie 丢失的回归。
  const thumbnail = firstCard.getByRole('img', { name: `${pageTitle} 截图`, exact: true })
  await expect(thumbnail).toBeVisible()
  await expect.poll(() => thumbnail.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  expect(new URL((await thumbnail.getAttribute('src'))!, page.url()).origin).toBe(new URL(page.url()).origin)
  await testInfo.attach('remote-render.png', { body: png, contentType: 'image/png' })
})

test('三维模型页面截图应包含真实模型像素', async ({ context, visualEditSandbox }, testInfo) => {
  test.setTimeout(180_000)
  const api = context.request
  const suffix = `w${testInfo.workerIndex}-${randomUUID().slice(0, 8)}`
  const assetName = `e2e-red-model-${suffix}`
  const modelPageTitle = `E2E 模型截图页 ${suffix}`

  // 上传红色 unlit 模型：渲染结果与光照/色调映射无关，像素断言基色稳定。
  const uploadResponse = await api.post(`/api/workspaces/${visualEditSandbox.workspaceId}/assets/upload`, {
    multipart: {
      file: { name: `${assetName}.glb`, mimeType: 'model/gltf-binary', buffer: buildRedModelGlb() },
      asset_type: 'model3d',
      tags: '[]',
      name: assetName,
    },
  })
  expect(uploadResponse.ok(), await uploadResponse.text()).toBeTruthy()

  const pageContent = `<template>
  <main class="w-full h-full p-8">
    <AssetModel name="${assetName}" class="w-full h-80" />
  </main>
</template>

<script setup lang="ts">
import AssetModel from '@runtime-kit/public/components/assets/AssetModel.v1.vue'
</script>
`
  const pageResponse = await api.post('/api/pages', {
    data: {
      workspace_id: visualEditSandbox.workspaceId,
      project_id: visualEditSandbox.projectId,
      title: modelPageTitle,
      file_type: 'vue',
      page_content: pageContent,
    },
  })
  expect(pageResponse.ok(), await pageResponse.text()).toBeTruthy()
  const modelPage = (await pageResponse.json()) as { id: number }

  try {
    // 通过截图任务走完整 Backend→Renderer→Runtime 链路；模型就绪由 render-ready 探针保证。
    // 使用项目默认视口：页面详情的最新判定按默认视口比对，显式覆盖会被保守标为非最新。
    const jobResponse = await api.post(`/api/pages/${modelPage.id}/screenshot-jobs`, {
      data: {},
    })
    expect(jobResponse.ok(), await jobResponse.text()).toBeTruthy()
    const job = (await jobResponse.json()) as { id: number }
    await expect.poll(async () => {
      const statusResponse = await api.get(`/api/pages/screenshot-jobs/${job.id}`)
      expect(statusResponse.ok()).toBeTruthy()
      const result = await statusResponse.json()
      return { status: result.status, error: result.error_code }
    }, { timeout: 120_000, intervals: [1000, 2000] }).toEqual({ status: 'succeeded', error: null })

    const detailsResponse = await api.get(`/api/pages/${modelPage.id}`)
    expect(detailsResponse.ok()).toBeTruthy()
    const details = await detailsResponse.json()
    expect(details.screenshot_is_latest).toBe(true)
    const imageResponse = await api.get(details.screenshot_url)
    expect(imageResponse.ok()).toBeTruthy()
    const png = Buffer.from(await imageResponse.body())

    // 像素级断言：模型真实渲染出现，而不是 WebGL 空白帧或占位。
    // 先附上截图再断言：断言失败时证据已归档，便于直接看图排障。
    await testInfo.attach('model-screenshot.png', { body: png, contentType: 'image/png' })
    const decoded = decodePngPixels(png)
    const redPixels = countStrongRedPixels(decoded)
    // 用占比而非绝对像素数：默认视口下红色三角约占 1%～3%，占比阈值不随视口尺寸漂移。
    const totalPixels = decoded.width * decoded.height
    expect(redPixels / totalPixels, `红色模型像素数量=${redPixels}/${totalPixels}`).toBeGreaterThan(0.005)
  } finally {
    await api.patch(`/api/pages/${modelPage.id}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})
