/**
 * 文件功能：覆盖全局 AI 侧栏打开、确认态 shell 可见性的 deterministic 冒烟路径。
 */
import { expect, test } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstPage, openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

test('AI 侧栏应可打开并展示会话面板', async ({ page }) => {
  await loginAsAdmin(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await openFirstPage(page)
  await page.locator('[data-testid="agent-sidebar-toggle"]').click()
  await expect(page.locator('[data-testid="agent-sidebar-panel"]')).toBeVisible()
})
