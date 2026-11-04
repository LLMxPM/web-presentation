/**
 * 文件功能：通过独立页面验证 Backend→Renderer→Runtime 基础截图链路，以及单页预览/截图宿主按
 * module 入口解析真实页码（PNG 内文字不可机读，页码在捕获宿主的 DOM 上断言）。
 */
import type { APIRequestContext } from '@playwright/test'

import { expect, test } from '../../fixtures/test-data'

/** 页脚直接渲染 useCurrentPage：验证捕获侧按路由目录解析，而不是把序号烘进源码。 */
function buildPageNumberPageContent(heading: string): string {
  return `<template>
  <main class="page-number-smoke">
    <h1>${heading}</h1>
    <footer data-testid="page-footer">{{ currentPage }} / {{ totalPages }}</footer>
  </main>
</template>

<script setup lang="ts">
import { useCurrentPage } from '@runtime-kit/public/composables/page/useCurrentPage.v1'

const { currentPage, totalPages } = useCurrentPage()
</script>
`
}

/**
 * 按给定顺序写入两条页面路由，返回响应；顺序决定两个页面的页码。
 */
async function putRoutes(
  request: APIRequestContext,
  projectId: number,
  routes: Array<{ route: string; order: number; pageId: number }>,
) {
  return request.put(`/api/projects/${projectId}/routes`, {
    data: {
      routes: routes.map(item => ({
        route_type: 'page',
        route: item.route,
        order: item.order,
        hidden: false,
        page_id: item.pageId,
      })),
    },
  })
}

test('页面截图应通过远程 Renderer 生成可下载 PNG', async ({ page, context, projectSandbox }, testInfo) => {
  test.setTimeout(180_000)
  const { workspaceId, projectId, pageId, pageTitle } = projectSandbox
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

test('单页预览与截图宿主应按路由目录解析真实页码', async ({ page, context, projectSandbox }) => {
  test.setTimeout(120_000)
  const { workspaceId, projectId, pageId } = projectSandbox

  const created = await context.request.post('/api/pages', {
    data: {
      workspace_id: workspaceId,
      project_id: projectId,
      title: '页码反查页',
      file_type: 'vue',
      summary: 'E2E 验证单页预览按 module 入口反查真实页码。',
      page_content: buildPageNumberPageContent('页码反查页'),
    },
  })
  expect(created.ok(), await created.text()).toBeTruthy()
  const footerPage = await created.json()

  try {
    const details = await context.request.get(`/api/pages/${footerPage.id}`)
    expect(details.ok(), await details.text()).toBeTruthy()
    const versionNo = (await details.json()).current_version_no as number

    // 每次预览都重出 artifact，确保读取的是当前路由目录而不是上一轮的配置。
    // 预览宿主把 Runtime 放在 iframe 里，页脚要在 frame 内定位。
    const openPreview = async () => {
      const response = await context.request.post(`/api/pages/${footerPage.id}/versions/${versionNo}/preview-artifact`)
      expect(response.ok(), await response.text()).toBeTruthy()
      const previewUrl = (await response.json()).preview_url as string
      await page.goto(previewUrl)
      return page.frameLocator('iframe').getByTestId('page-footer')
    }

    // 第一轮：页脚页排在第二位，必须显示 2 / 2（恒为 0 或烘死常量都会失败）。
    let routeResponse = await putRoutes(context.request, projectId, [
      { route: 'home', order: 0, pageId },
      { route: 'numbers', order: 1, pageId: footerPage.id },
    ])
    expect(routeResponse.ok(), await routeResponse.text()).toBeTruthy()
    await expect(await openPreview()).toHaveText('2 / 2', { timeout: 60_000 })

    // 第二轮：交换顺序后同一页面应变成 1 / 2，证明页码来自当前路由目录而不是源码常量。
    routeResponse = await putRoutes(context.request, projectId, [
      { route: 'home', order: 1, pageId },
      { route: 'numbers', order: 0, pageId: footerPage.id },
    ])
    expect(routeResponse.ok(), await routeResponse.text()).toBeTruthy()
    await expect(await openPreview()).toHaveText('1 / 2', { timeout: 60_000 })
  } finally {
    await putRoutes(context.request, projectId, [{ route: 'home', order: 0, pageId }]).catch(() => undefined)
    await context.request.patch(`/api/pages/${footerPage.id}`, { data: { status: 'archived' } }).catch(() => undefined)
  }
})
