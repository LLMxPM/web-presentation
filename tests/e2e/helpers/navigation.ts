/**
 * 文件功能：封装平台 E2E 常用页面跳转与等待逻辑，减少 spec 中的重复步骤。
 */
import { expect, type Page } from '@playwright/test'

/**
 * 已登录用例的统一入口：storageState 已携带登录态，直接进入工作空间首页，不重复登录。
 */
export async function gotoWorkspaceHome(page: Page) {
  await page.goto('/')
  await waitForWorkspaceHome(page)
}

export async function waitForWorkspaceHome(page: Page) {
  await expect(page.locator('[data-testid="workspace-project-list"]')).toBeVisible()
}

export async function openSmokeProject(page: Page) {
  const smokeProject = page.getByRole('link', { name: '打开项目：Smoke Project', exact: true })
  await expect(smokeProject).toBeVisible()
  await smokeProject.click()
  await expect(page.locator('[data-testid="project-pages-view"]')).toBeVisible()
}

export async function openSmokePage(page: Page) {
  const smokePage = page.locator('[data-testid="page-card"]').filter({
    has: page.getByRole('button', { name: '复制页面名称：Smoke Page', exact: true }),
  })
  await expect(smokePage).toBeVisible()
  await smokePage.click()
  await expect(page.locator('[data-testid="page-detail-view"]')).toBeVisible()
}
