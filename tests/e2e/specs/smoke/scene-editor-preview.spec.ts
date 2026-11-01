/**
 * 文件功能：在真实 Editor 页面详情里验证 Scene 预览控件与 Runtime iframe 的播放/停止状态。
 * 控件只有播放与停止；不存在进度、定位、暂停、重播或降动效控制。
 */
import { expect, test } from '../../fixtures/test-data'
import { buildScenePage } from '../../helpers/scene-page-source'

test('页面详情预览可播放和停止页内 Scene', async ({ page, context, projectSandbox }) => {
  test.setTimeout(120_000)
  const update = await context.request.patch(`/api/pages/${projectSandbox.pageId}`, {
    data: { page_content: buildScenePage() },
  })
  expect(update.ok(), await update.text()).toBeTruthy()
  await page.goto(`/workspaces/${projectSandbox.workspaceId}/projects/${projectSandbox.projectId}/pages/${projectSandbox.pageId}`)
  const controls = page.getByTestId('preview-scene-controls')
  await expect(controls).toBeVisible({ timeout: 45_000 })
  const preview = page.frameLocator('iframe[title="runtime-preview"]').frameLocator('iframe#preview')
  const title = preview.locator('.scene-e2e-title')
  const counter = preview.locator('.scene-e2e-counter')
  await expect(title).toBeVisible()
  // 未播放时 Scene 不执行：模板保持完整可读，计数器停在初值。
  await expect(controls).toContainText('未播放')
  await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')
  await expect(counter).toHaveText('0')

  await controls.getByRole('button', { name: '播放页内 Scene' }).click()
  await expect(controls).toContainText('有限任务已完成', { timeout: 30_000 })
  await expect(counter).toHaveText('100')
  await expect.poll(() => title.evaluate(element => getComputedStyle(element).opacity)).toBe('1')

  await controls.getByRole('button', { name: '停止页内 Scene' }).click()
  await expect(controls).toContainText('已停止')
  // 停止必须恢复页面初值，不能把播放终态留在画布上。
  await expect(counter).toHaveText('0')
})
