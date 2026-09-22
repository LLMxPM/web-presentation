/**
 * 文件功能：通过独立页面验证 Backend→Renderer→Runtime 真实截图与 PNG 产物链路。
 */
import { expect, test } from '../../fixtures/test-data'

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
  await testInfo.attach('remote-render.png', { body: png, contentType: 'image/png' })
})
