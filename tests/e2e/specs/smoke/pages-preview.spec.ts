/**
 * 文件功能：覆盖页面列表进入、页面详情打开与预览 iframe 可见的只读主链路；登录态由 storageState 提供。
 */
import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome, openSmokePage, openSmokeProject } from '../../helpers/navigation'

test('创建后的页面应可进入详情并展示预览 iframe', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await openSmokeProject(page)
  await openSmokePage(page)
  await expect(page.locator('[data-testid="page-preview-frame"]')).toBeVisible()
  const preview = page.frameLocator('[data-testid="page-preview-frame"] iframe').frameLocator('iframe#preview')
  await expect(preview.getByRole('heading', { name: /Smoke/ })).toBeVisible()
  const userFrame = page.frames().find(frame => {
    try { return new URL(frame.url()).hostname === 'preview.localhost' } catch { return false }
  })
  expect(userFrame).toBeTruthy()
  expect(await userFrame!.evaluate(() => window.location.hostname)).toBe('preview.localhost')
  expect((await page.context().cookies('http://preview.localhost:7373')).some(cookie => cookie.name === 'wp_user_session')).toBe(false)
})
