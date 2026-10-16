/**
 * 文件功能：覆盖页面列表进入、预览内容渲染及消息桥就绪后的遮罩消失；登录态由 storageState 提供。
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
  // 内容渲染与宿主收到 ready 是独立链路，防止页面已显示却仍被误判为加载超时。
  await expect(page.getByTestId('page-preview-status-overlay')).toBeHidden()
  const userFrame = page.frames().find(frame => {
    try { return new URL(frame.url()).hostname === 'preview.localhost' } catch { return false }
  })
  expect(userFrame).toBeTruthy()
  expect(await userFrame!.evaluate(() => window.location.hostname)).toBe('preview.localhost')
  expect((await page.context().cookies('http://preview.localhost:7373')).some(cookie => cookie.name === 'wp_user_session')).toBe(false)
})
