/**
 * 文件功能：在真实 Editor 页面详情里验证时间轴预览控制条与 Runtime iframe 的双向状态。
 */
import { expect, test } from '../../fixtures/test-data'
import { buildMotionPage } from '../../helpers/motion-page-source'

test('页面详情预览可播放、暂停、重播、定位并模拟降动效', async ({ page, context, visualEditSandbox }) => {
  test.setTimeout(120_000)
  const update = await context.request.patch(`/api/pages/${visualEditSandbox.pageId}`, {
    data: { page_content: buildMotionPage() },
  })
  expect(update.ok(), await update.text()).toBeTruthy()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto(`/workspaces/${visualEditSandbox.workspaceId}/projects/${visualEditSandbox.projectId}/pages/${visualEditSandbox.pageId}`)
  const controls = page.getByTestId('preview-motion-controls')
  await expect(controls).toBeVisible({ timeout: 45_000 })
  const reduced = controls.getByRole('button', { name: '降动效' })
  await expect(reduced).toHaveAttribute('aria-pressed', 'true')
  const preview = page.frameLocator('iframe[title="runtime-preview"]').frameLocator('iframe#preview')
  await expect(preview.locator('.motion-e2e-title')).toBeVisible()
  await reduced.click()
  await expect(reduced).toHaveAttribute('aria-pressed', 'false')
  await controls.getByRole('button', { name: '从起点重播页内时间轴' }).click()
  await expect(controls.getByRole('button', { name: '暂停页内时间轴' })).toBeVisible()
  await controls.getByRole('button', { name: '暂停页内时间轴' }).click()
  await expect(controls.getByRole('button', { name: '播放页内时间轴' })).toBeVisible()
  const position = controls.getByRole('slider', { name: '页内时间轴位置' })
  await position.evaluate(element => {
    const input = element as HTMLInputElement
    input.value = '400'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await expect.poll(() => position.inputValue()).toBe('400')
  await expect.poll(async () => Number(await preview.locator('.motion-e2e-title').evaluate(element => getComputedStyle(element).opacity)))
    .toBeGreaterThan(0.1)
  await expect.poll(async () => Number(await preview.locator('.motion-e2e-title').evaluate(element => getComputedStyle(element).opacity)))
    .toBeLessThan(0.8)
})
