/**
 * 文件功能：覆盖全局 AI 侧栏打开、确认态 shell 可见性的冒烟路径；会话链路走真实 Backend。
 */
import { expect, test } from '../../fixtures/base'

import { gotoWorkspaceHome, openSmokePage, openSmokeProject } from '../../helpers/navigation'

test('工作空间级内容助手无需进入项目即可打开，并可随页面导航继续使用', async ({ page }) => {
  await gotoWorkspaceHome(page)
  await page.locator('[data-testid="agent-floating-trigger"]').click()
  const panel = page.locator('[data-testid="agent-sidebar-panel"]')
  await expect(panel).toBeVisible()
  await expect(panel).not.toContainText('需要先进入项目')

  await openSmokeProject(page)
  await openSmokePage(page)
  await expect(panel).toBeVisible()
})
