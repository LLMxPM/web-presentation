/**
 * 文件功能：覆盖真实项目构建重型链路：在夹具沙箱项目发起构建，等待 Runtime 构建完成并校验产物状态。
 */
import type { Page } from '@playwright/test'

import { expect, test } from '../../fixtures/test-data'

interface BuildJob {
  id: number
  status: string
}

/**
 * 在预览页内以同源 fetch 读取产物响应头。
 *
 * preview.localhost 只保证在浏览器内解析（Chromium 按回环地址处理 *\.localhost），
 * 系统 DNS 与 Playwright ApiRequestContext 直接解析域名会在无 hosts 记录的机器上
 * 报 getaddrinfo ENOTFOUND，因此产物的响应头断言必须在页面内完成。
 */
async function readPreviewAsset(page: Page, url: string) {
  return await page.evaluate(async (target) => {
    const response = await fetch(target, { credentials: 'same-origin', cache: 'no-store' })
    return {
      ok: response.ok,
      status: response.status,
      cacheControl: response.headers.get('cache-control'),
    }
  }, url)
}

test('沙箱项目应完成一次真实构建并展示构建成功', async ({ page, context, browser, visualEditSandbox }) => {
  await page.goto(`/workspaces/${visualEditSandbox.workspaceId}/projects/${visualEditSandbox.projectId}/pages`)
  await expect(page.locator('[data-testid="project-pages-view"]')).toBeVisible()
  await page.locator('[data-testid="project-build-open"]').click()
  await expect(page.locator('[data-testid="project-build-dialog"]')).toBeVisible()
  await page.getByRole('button', { name: '发起构建' }).click()

  // 真实构建经由 Backend 构建队列委托 Runtime 执行，轮询任务状态直至终态。
  const api = context.request
  await expect(async () => {
    const response = await api.get(`/api/projects/${visualEditSandbox.projectId}/build-jobs/latest`)
    expect(response.ok()).toBeTruthy()
    const job = (await response.json()) as BuildJob | null
    expect(job, '构建任务尚未创建').not.toBeNull()
    expect(job!.status, `构建任务 #${job!.id} 当前状态`).toBe('succeeded')
  }).toPass({ timeout: 360_000, intervals: [2_000] })

  // 产物可下载说明构建输出已真实托管。
  const artifact = await api.get(`/api/projects/${visualEditSandbox.projectId}/build-jobs/latest`)
  const latestJob = (await artifact.json()) as BuildJob
  const artifactResponse = await api.get(
    `/api/projects/${visualEditSandbox.projectId}/build-jobs/${latestJob.id}/artifact`,
  )
  expect(artifactResponse.ok()).toBeTruthy()

  const accessResponse = await api.post(
    `/api/projects/${visualEditSandbox.projectId}/build-jobs/${latestJob.id}/access`,
  )
  expect(accessResponse.ok()).toBeTruthy()
  const access = await accessResponse.json()
  expect(new URL(access.browse_url).hostname).toBe('preview.localhost')
  const builtPage = await context.newPage()
  const navigation = await builtPage.goto(access.browse_url)
  expect(navigation?.headers()['cache-control']).toBe('no-store')
  // 构建站点缩略图也会渲染同一页；校验主画布中的最后一个实例。
  await expect(builtPage.getByRole('heading', { name: visualEditSandbox.pageTitle, exact: true }).last()).toBeVisible()
  const builtImage = builtPage.getByRole('img', { name: 'Smoke illustration', exact: true }).last()
  await expect(builtImage).toBeVisible()
  await expect(builtImage).toHaveJSProperty('naturalWidth', 320)
  const cssUrl = await builtPage.locator('link[rel="stylesheet"]').first().getAttribute('href')
  const privateCssUrl = new URL(cssUrl!, builtPage.url()).href
  const cssResponse = await readPreviewAsset(builtPage, privateCssUrl)
  expect(cssResponse.ok).toBeTruthy()
  expect(cssResponse.cacheControl).toBe('private, no-cache')
  const anonymous = await browser.newContext()
  try {
    // 匿名上下文同样经浏览器发起，未携带构建票据时应被拒绝。
    const anonymousPage = await anonymous.newPage()
    const denied = await anonymousPage.goto(privateCssUrl)
    expect(denied?.status()).toBe(404)
  } finally {
    await anonymous.close()
    await builtPage.close()
  }

  // 提交后弹窗会自动关闭；重新打开并刷新，验证用户可见的历史状态与下载入口。
  await page.locator('[data-testid="project-build-open"]').click()
  const buildDialog = page.locator('[data-testid="project-build-dialog"]')
  await expect(buildDialog).toBeVisible()
  await buildDialog.getByRole('button', { name: '刷新最新状态' }).click()
  await expect(buildDialog.getByText('成功', { exact: true })).toBeVisible()
  await expect(buildDialog.getByRole('button', { name: 'ZIP', exact: true })).toBeVisible()
})
